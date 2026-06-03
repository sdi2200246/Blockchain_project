import socket
import threading
import time
import pickle
import queue
import protocols
from blockchain import BlockChain, Block
from exceptions import BlockchainError, InvalidBlockError


def _graceful_close(sock):
    """Half-close before closing so the peer's recv() drains cleanly
    instead of getting an RST. Safe to call on already-closed sockets."""
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class Node:
    def __init__(self, host, port, chain=None):
        self.host = host
        self.port = port
        self.peers = set()
        self.blcok_chain: BlockChain = BlockChain() if chain is None else chain
        self.server_socket = None
        self.running = True
        self.jobs = queue.Queue()
        self.worker_dispatch = {}
        self.logs = list()
        threading.Thread(target=self.receive_requests_loop, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()


    @staticmethod
    def _graceful_close(sock):
        """Half-close before closing so the peer's recv() drains cleanly
        instead of getting an RST. Safe to call on already-closed sockets."""
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def connect_to_peer(self, peer_address):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.connect(('localhost', peer_address))
            return client_socket
        except Exception as e:
            print(f"Error connecting to host: {e}")
            client_socket.close()
            return None

    def broadcast_message(self, message, receive=False):
        for peer_host, peer_port in self.peers:
            try:
                sock = self.connect_to_peer(peer_port)
                if sock:
                    if receive:
                        self.send_and_receive_message_to_peer(sock, message)
                    else:
                        self.send_message_to_peer(sock, message)
                        self._graceful_close(sock)

            except Exception as e:
                print(f"Error broadcasting to peer {peer_host}:{peer_port} - {e}")

    def send_message_to_peer(self, client_socket, message):
        try:
            header = message[0].ljust(25, b'\0')
            client_socket.sendall(header)
            message_bytes = pickle.dumps(message[1])
            length = len(message_bytes)
            length_bytes = length.to_bytes(4, byteorder='big')
            client_socket.sendall(length_bytes)
            client_socket.sendall(message_bytes)
        except Exception as e:
            print(f"Error communicating to host: {e} socket {client_socket} message : {message} self {self.port}")

    def send_and_receive_message_to_peer(self, client_socket, message):
        try:
            header = message[0].ljust(25, b'\0')
            client_socket.sendall(header)

            message_bytes = pickle.dumps(message[1])
            length = len(message_bytes)
            length_bytes = length.to_bytes(4, byteorder='big')
            client_socket.sendall(length_bytes)
            client_socket.sendall(message_bytes)
            threading.Thread(target=self.receive_message, args=(client_socket,), daemon=True).start()

        except Exception as e:
            print(f"Error communicating to host: {e} socket{client_socket} message :{message} self {self.port}")

    def receive_message(self, client_socket):
        try:
            header_str = client_socket.recv(25).rstrip(b'\0')
            threading.Thread(target=protocols.generic_protocol_handler, args=(header_str, client_socket, self), daemon=True).start()
        except Exception as e:
            print(f"Error receiving request: {e}")
            client_socket.close()

    def receive_requests_loop(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('localhost', self.port))
        self.server_socket.listen(socket.SOMAXCONN)
        print("Waiting for connections\n")
        while self.running:
            conn, addr = self.server_socket.accept()
            # Don't recv here — spawn a thread that does the recv and handles the message
            threading.Thread(target=self._handle_incoming, args=(conn,), daemon=True).start()


    def _handle_incoming(self, conn):
        try:
            header_str = protocols.recv_exact(conn, 25).rstrip(b'\0')
            protocols.generic_protocol_handler(header_str, conn, self)
        except Exception as e:
            print(f"Error receiving request: {e}")
            conn.close()


    def worker(self):
        while self.running:
            job = self.jobs.get()
            job_type, job_data = job

            handler = self.worker_dispatch.get(job_type)
            if handler:
                try:
                    handler(job_data)
                except Exception as e:
                    print(f"Worker error handling {job_type}: {e}")
            else:
                print(f"No worker handler for {job_type}")


class BootstrapperNode(Node):
    def __init__(self, host, port):
        super().__init__(host, port)
        self.worker_dispatch.update({
            b"register": self.register,
            b"send_peers": self.send_peers
        })

    def register(self, job_data):
        conn_socket, addr = job_data
        if addr not in self.peers:
            self.peers.add(addr)

        print(self.peers)
        conn_socket.close()

    def send_peers(self, job_data):
        conn_socket, _ = job_data
        self.send_message_to_peer(conn_socket, (b"peers", self.peers))
        self._graceful_close(conn_socket)


class CoreNode(Node):
    def __init__(self, host, port):
        super().__init__(host, port)
        self.worker_dispatch.update({
            b"get_peers": self.get_peers,
            b"send_chain": self.send_chain,
            b"get_new_chain": self.get_new_chain,
            b"get_transaction": self.get_transaction,
            b"get_block": self.get_block,
        })
        self.seen_blocks = set()
        self.log_lock = threading.Lock()

    def log(self, message):
        with self.log_lock:
            self.logs.append(message)

    def get_peers(self, job_data):
        conn_socket, peers = job_data
        self.peers.update(peers - {(self.host, self.port)})
        conn_socket.close()

    def send_chain(self, job_data):
        conn_socket, _ = job_data
        if isinstance(self, MinerNode):
            self.chain_lock.acquire()
        try:
            self.send_message_to_peer(conn_socket, (b"new_chain", self.blcok_chain))
        finally:
            if isinstance(self, MinerNode):
                self.chain_lock.release()
            self._graceful_close(conn_socket)

    def get_new_chain(self, job_data):
        conn_socket, new_chain = job_data
        if isinstance(self, MinerNode):
            self.chain_lock.acquire()
        try:
            try:
                new_chain.chain_validation(self.blcok_chain)
                self.blcok_chain = new_chain
                self.log("Resolved a fork situation\n")
                print("Resolved a fork situation\n")

            except BlockchainError as e:
                self.log(str(e))
        finally:
            if isinstance(self, MinerNode):
                self.chain_lock.release()
            conn_socket.close()

    def get_transaction(self, job_data):
        conn_socket, tx = job_data
        if isinstance(self, MinerNode):
            self.chain_lock.acquire()
            self.stat_mining_event.set()
        try:
            try:
                self.blcok_chain.validate_transaction(tx)
                self.blcok_chain.transaction_pool.add(tx)
                self.broadcast_message((b"transaction", tx))

            except BlockchainError as e:
                self.log(str(e))
        finally:
            if isinstance(self, MinerNode):
                self.chain_lock.release()
            conn_socket.close()

    def get_block(self, job_data):
        conn_socket, new_block = job_data
        do_broadcast = False
        if isinstance(self, MinerNode):
            self.chain_lock.acquire()
        try:
            try:
                self.blcok_chain.block_validation(new_block, self.seen_blocks)
                self.blcok_chain.update_utxo_pool(new_block)
                self.blcok_chain.uptade_transaction_pool(new_block)
                self.blcok_chain.uptade_chain(new_block)
                do_broadcast = True

            except InvalidBlockError as e:
                self.log(str(e))
                self.broadcast_message((b"get_chain", None), receive=True)

            except BlockchainError as e:
                self.log(str(e))

        finally:
            if isinstance(self, MinerNode):
                self.chain_lock.release()
            conn_socket.close()

        if do_broadcast:
            self.broadcast_message((b"block", new_block))


class MinerNode(CoreNode):
    def __init__(self, host, port, chain=None):
        super().__init__(host, port)
        self.blcok_chain = chain
        self.chain_lock = threading.Lock()
        self.stat_mining_event = threading.Event()

        threading.Thread(target=self.miner, daemon=True).start()

    def miner(self):
        while self.running:
            self.stat_mining_event.wait()

            with self.chain_lock:
                if len(self.blcok_chain.transaction_pool) >= 2:
                    new_block = self.blcok_chain.create_candidate_block()
                else:
                    self.stat_mining_event.clear()
                    continue

            self.blcok_chain.mine_block(new_block)

            with self.chain_lock:
                if self.blcok_chain.get_last_block().block_hash() != new_block.previous_hash:
                    print("FORK DETECTED \n")
                    continue

                self.blcok_chain.update_utxo_pool(new_block)
                self.blcok_chain.uptade_transaction_pool(new_block)
                self.blcok_chain.uptade_chain(new_block)
                self.seen_blocks.add(new_block.block_hash())

            print(f"Just mined a block: {self.port} : {new_block.block_hash()}\n")
            self.broadcast_message((b"block", new_block))