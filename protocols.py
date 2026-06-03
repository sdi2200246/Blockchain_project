import threading
import pickle
import ecdsa


PROTOCOL_MAP = {
    b"registration":    ("register",      True),
    b"get_peers":       ("send_peers",    False),
    b"peers":           ("get_peers",     True),
    b"get_chain":       ("send_chain",    False),
    b"new_chain":       ("get_new_chain", True),
    b"transaction":     ("get_transaction", True),
    b"block":           ("get_block",     True),
}


def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            raise ConnectionError("Socket closed early")
        data += packet
    return data


def unpuck_data(client_socket):
    length_bytes = recv_exact(client_socket, 4)
    length = int.from_bytes(length_bytes, byteorder='big')
    data_bytes = recv_exact(client_socket, length)
    return pickle.loads(data_bytes)


def generic_protocol_handler(message_type, client_socket, instance):
    try:
        if message_type not in PROTOCOL_MAP:
            client_socket.close()
            return

        job_type, needs_data = PROTOCOL_MAP[message_type]

        if needs_data:
            data = unpuck_data(client_socket)
        else:
            data = None

        instance.jobs.put((job_type.encode(), (client_socket, data)))

    except Exception as e:
        print(f"Error in protocol handler: {e} on message : {message_type}")
        client_socket.close()