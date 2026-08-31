"""Peer-to-peer middleware: plain TCP sockets directly between zone processes.

No coordinator or broker involved — one zone connects straight to another
zone's P2P port. Protocol is a single newline-terminated text line per
request/response, e.g. "CAPACITY_REQUEST" -> "AVAILABLE_SLOTS=8".
"""

import socket
import threading


def start_p2p_server(host: str, port: int, handle_message):
    """Start a background thread accepting P2P connections.

    `handle_message(message: str) -> str` returns the reply line to send back.
    """

    def _serve():
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen(5)
        while True:
            conn, addr = server_sock.accept()
            threading.Thread(target=_handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(conn, addr):
        with conn:
            data = conn.recv(1024)
            if not data:
                return
            message = data.decode("utf-8").strip()
            reply = handle_message(message)
            conn.sendall((reply + "\n").encode("utf-8"))

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return thread


def send_p2p_message(host: str, port: int, message: str, timeout: float = 2.0) -> str | None:
    """Connect to a peer zone, send one message line, return its reply (or None on failure)."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall((message + "\n").encode("utf-8"))
            data = sock.recv(1024)
            return data.decode("utf-8").strip()
    except OSError as exc:
        print(f"[P2P] Failed to reach {host}:{port} -> {exc}")
        return None
