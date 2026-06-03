import pytest
import socket
import time
import queue
import threading
from node2 import Node, CoreNode, BootstrapperNode
from blockchain import BlockChain
from block import Block
from protocols import unpuck_data, generic_protocol_handler


def wait(seconds=0.3):
    time.sleep(seconds)



class TestConnectToPeer:
   def test_connect_to_nonexistent_peer_returns_none(self):
    """connect_to_peer should return None when the connection fails,
    so callers can check `if sock is not None` and skip dead peers."""
    node = Node('localhost', 19999)
    sock = node.connect_to_peer(1)
    assert sock is None


class TestBootstrapperRegistration:
    def test_single_node_registers(self):
        """A node sends `registration` to the bootstrapper. The bootstrapper
        should add it to its peer set."""
        bootstrapper = BootstrapperNode('localhost', 21000)
        wait()

        node = CoreNode('localhost', 21001)
        wait()

        sock = node.connect_to_peer(21000)
        assert sock is not None, "connect_to_peer returned something (currently buggy)"
        node.send_and_receive_message_to_peer(sock, (b"registration", (node.host, node.port)))
        wait(0.5)  # let bootstrapper's worker process the job

        assert ('localhost', 21001) in bootstrapper.peers

    def test_multiple_nodes_register(self):
        """Three nodes register with the bootstrapper; all should appear."""
        bootstrapper = BootstrapperNode('localhost', 21100)
        wait()

        nodes = []
        for i in range(3):
            node = CoreNode('localhost', 21101 + i)
            wait()
            sock = node.connect_to_peer(21100)
            node.send_and_receive_message_to_peer(
                sock, (b"registration", (node.host, node.port))
            )
            nodes.append(node)

        wait(1.0)

        for i in range(3):
            assert ('localhost', 21101 + i) in bootstrapper.peers, \
                f"Node {21101 + i} did not register"

    def test_duplicate_registration_does_not_duplicate(self):
        """Registering the same node twice should not create duplicate entries."""
        bootstrapper = BootstrapperNode('localhost', 21200)
        wait()

        node = CoreNode('localhost', 21201)
        wait()

        for _ in range(2):
            sock = node.connect_to_peer(21200)
            node.send_and_receive_message_to_peer(
                sock, (b"registration", (node.host, node.port))
            )
            wait(0.3)

        # Set semantics: should only appear once
        assert len([p for p in bootstrapper.peers if p == ('localhost', 21201)]) == 1


# ---------- Peer discovery tests ----------

class TestPeerDiscovery:
    def test_node_gets_peer_list_from_bootstrapper(self):
        """node2 asks the bootstrapper for peers and gets back node1's address."""
        bootstrapper = BootstrapperNode('localhost', 22000)
        wait()

        node1 = CoreNode('localhost', 22001)
        wait()

        # node1 registers
        sock = node1.connect_to_peer(22000)
        node1.send_and_receive_message_to_peer(
            sock, (b"registration", (node1.host, node1.port))
        )
        wait(0.5)

        # node2 asks for peers
        node2 = CoreNode('localhost', 22002)
        wait()

        sock = node2.connect_to_peer(22000)
        node2.send_and_receive_message_to_peer(sock, (b"get_peers", None))
        wait(1.0)

        assert ('localhost', 22001) in node2.peers, \
            f"node2 did not receive node1 in peer list. Got: {node2.peers}"

    def test_node_excludes_self_from_received_peer_list(self):
        """When a node receives a peer list that includes its own address,
        it should not add itself."""
        bootstrapper = BootstrapperNode('localhost', 22100)
        wait()

        node1 = CoreNode('localhost', 22101)
        wait()

        # node1 registers itself
        sock = node1.connect_to_peer(22100)
        node1.send_and_receive_message_to_peer(
            sock, (b"registration", (node1.host, node1.port))
        )
        wait(0.5)

        # node1 asks for the peer list (which now includes itself)
        sock = node1.connect_to_peer(22100)
        node1.send_and_receive_message_to_peer(sock, (b"get_peers", None))
        wait(0.5)

        assert ('localhost', 22101) not in node1.peers, \
            "Node added itself to its own peer set"


# ---------- Chain sync tests ----------

class TestChainSync:
    def test_node_syncs_chain_from_peer(self):
        """node2 requests node1's chain. After sync, node2's chain length
        should match node1's."""
        # Set up node1 with a 2-block chain
        node1 = CoreNode('localhost', 23001)
        wait()

        # Build a chain: genesis + 1 block
        bc = BlockChain()
        genesis = Block(0, [], time.time(), "0" * 64)
        genesis.Merkle_tree_creation()
        bc.mine_block(genesis)
        bc.uptade_chain(genesis)

        block1 = Block(1, [], time.time(), genesis.block_hash())
        block1.Merkle_tree_creation()
        bc.mine_block(block1)
        bc.uptade_chain(block1)

        node1.blcok_chain = bc

        # node2 starts empty and requests the chain
        node2 = CoreNode('localhost', 23002)
        wait()

        sock = node2.connect_to_peer(23001)
        node2.send_and_receive_message_to_peer(sock, (b"get_chain", None))
        wait(1.5)

        assert len(node2.blcok_chain.chain) == 2, \
            f"Expected chain length 2, got {len(node2.blcok_chain.chain)}"
        assert node2.blcok_chain.chain[0].block_hash() == genesis.block_hash()
        assert node2.blcok_chain.chain[1].block_hash() == block1.block_hash()

    def test_sync_rejects_equal_or_shorter_chain(self):
        """If a node already has a chain >= the received one, it should not
        replace its chain. (chain_validation's `old_chain` check.)"""
        node1 = CoreNode('localhost', 23101)
        wait()

        # node1 has a 1-block chain
        bc1 = BlockChain()
        g1 = Block(0, [], time.time(), "0" * 64)
        g1.Merkle_tree_creation()
        bc1.mine_block(g1)
        bc1.uptade_chain(g1)
        node1.blcok_chain = bc1

        # node2 also has a 1-block chain (different block)
        node2 = CoreNode('localhost', 23102)
        wait()

        bc2 = BlockChain()
        g2 = Block(0, [], time.time(), "0" * 64)
        g2.Merkle_tree_creation()
        bc2.mine_block(g2)
        bc2.uptade_chain(g2)
        node2.blcok_chain = bc2
        original_hash = g2.block_hash()

        # node2 asks node1 for its chain
        sock = node2.connect_to_peer(23101)
        node2.send_and_receive_message_to_peer(sock, (b"get_chain", None))
        wait(1.5)

        # Since both have length 1, node2 should keep its own
        assert node2.blcok_chain.chain[0].block_hash() == original_hash, \
            "node2 replaced its chain with an equal-length chain (shouldn't have)"
        


import pytest
import socket
import queue
import time
from node2 import Node, CoreNode, BootstrapperNode
from protocols import unpuck_data, generic_protocol_handler


class TestBug1_GetPeersCrashesOnNonePayload:
    """In fork-detection runs we see:
       'Worker error handling b'get_peers': unsupported operand type(s) for -: 'NoneType' and 'set''
       Reproduce it directly: feed None to get_peers."""

    def test_get_peers_raises_typeerror_when_payload_is_none(self):
        node = CoreNode('localhost', 27001)
        time.sleep(0.2)

        a, b = socket.socketpair()
        with pytest.raises(TypeError, match="unsupported operand type"):
            node.get_peers((a, None))

        a.close()
        b.close()


class TestBug2_GetNewChainCrashesOnNonePayload:
    """In fork-detection runs we see:
       'Worker error handling b'get_new_chain': 'NoneType' object has no attribute 'chain_validation''
       Reproduce: feed None to get_new_chain."""

    def test_get_new_chain_raises_attributeerror_when_payload_is_none(self):
        node = CoreNode('localhost', 27002)
        time.sleep(0.2)

        a, b = socket.socketpair()
        with pytest.raises(AttributeError, match="chain_validation"):
            node.get_new_chain((a, None))

        a.close()
        b.close()


class TestBug3_ProtocolHandlerNoLongerEnqueuesOnFailure:
    """Previously: when unpuck_data failed, the handler enqueued (socket, None)
    causing downstream handlers to crash on None payloads.
    After fix: unpuck_data raises, the handler catches and closes the socket,
    no job is enqueued."""

    def test_handler_does_not_enqueue_when_socket_dies_midread(self):
        class FakeNode:
            def __init__(self):
                self.jobs = queue.Queue()

        node = FakeNode()
        a, b = socket.socketpair()
        a.close()  # peer dies, no payload coming

        generic_protocol_handler(b"peers", b, node)

        assert node.jobs.empty(), \
            "Handler should NOT enqueue jobs when payload unpacking failed"

    def test_handler_does_not_enqueue_new_chain_when_socket_dies(self):
        class FakeNode:
            def __init__(self):
                self.jobs = queue.Queue()

        node = FakeNode()
        a, b = socket.socketpair()
        a.close()

        generic_protocol_handler(b"new_chain", b, node)

        assert node.jobs.empty(), \
            "Handler should NOT enqueue get_new_chain jobs when payload unpacking failed"

class TestBug4_BroadcastRaceClosesSocketTooEarly:
    """In fork-detection runs we see:
       'Error during data unpacking: [Errno 104] Connection reset by peer'
       This is caused by broadcast_message calling sock.close() immediately
       after sendall, before the receiver finished reading."""

    def test_recv_after_sender_closes_returns_eof_or_raises(self):
        """Demonstrate the underlying TCP behavior that bites broadcast_message."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('localhost', 0))
        server.listen(1)
        port = server.getsockname()[1]

        accepted = []
        def accept_one():
            conn, _ = server.accept()
            accepted.append(conn)
        import threading
        threading.Thread(target=accept_one, daemon=True).start()

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('localhost', port))
        # Send 25-byte header — mimicking the start of a real broadcast
        client.sendall(b"header_only".ljust(25, b'\0'))
        # Now close *before* sending the length prefix and payload —
        # exactly what broadcast_message does when receive=False
        client.close()

        time.sleep(0.1)
        conn = accepted[0]

        # Reader gets the header...
        header = conn.recv(25)
        assert len(header) == 25

        # ...but the length prefix never arrives. recv_exact would raise.
        from protocols import recv_exact
        with pytest.raises(ConnectionError, match="Socket closed early"):
            recv_exact(conn, 4)

        conn.close()
        server.close()


class TestBug5_BroadcastToDeadPeerStillTries:
    """When a peer disappears (was a peer, no longer listening), broadcast_message
    tries to send anyway. With the current connect_to_peer fix this should be
    handled, but let's verify the broadcast loop is robust."""

    def test_broadcast_to_dead_peer_does_not_crash_node(self):
        node = CoreNode('localhost', 27101)
        time.sleep(0.2)

        # Add a peer that doesn't exist
        node.peers.add(('localhost', 1))  # port 1, nothing there

        # broadcast_message should handle this gracefully
        try:
            node.broadcast_message((b"transaction", "fake_payload"))
        except Exception as e:
            pytest.fail(f"broadcast_message crashed instead of swallowing error: {e}")


class TestBug6_MinerForkContinueLeavesPoolUnmined:
    """When the miner's mid-PoW fork check fires, it `continue`s. But it doesn't
    re-set stat_mining_event. If the pool still has transactions, they sit
    unmined until something else wakes the miner. This is a latent bug — the
    miner can stop making progress even with work available."""

    def test_miner_event_state_after_fork_continue(self):
        """This is a behavioral test: after a simulated fork mid-mining,
        is the event still set so the miner will retry?"""
        from node2 import MinerNode
        import copy
        from test_miner import make_chain_with_pending_txs

        bc, _, _ = make_chain_with_pending_txs(num_txs=4)
        miner = MinerNode('localhost', 27201, chain=bc)
        time.sleep(0.2)

        # Trigger mining
        miner.stat_mining_event.set()

        # Wait for at least one block to be mined
        deadline = time.time() + 15
        while time.time() < deadline and len(miner.blcok_chain.chain) < 2:
            time.sleep(0.1)

        # The pool still has txs (we seeded 4, miner takes 2 per block)
        assert len(miner.blcok_chain.transaction_pool) >= 2, \
            "Pool should still have work"

        # After mining, the event should still be set so the miner picks up the next round
        # If it's been cleared, mining halts even though there's work to do
        time.sleep(0.5)

        # Either the miner is mining again (next block coming), or it has more work pending.
        # If event is clear AND pool has work, that's the bug.
        if not miner.stat_mining_event.is_set():
            if len(miner.blcok_chain.transaction_pool) >= 2:
                # Wait a bit more to see if it self-recovers
                time.sleep(2.0)
                assert len(miner.blcok_chain.chain) >= 3, (
                    "BUG: miner has work in pool but event is cleared "
                    "and no new block was mined"
                )