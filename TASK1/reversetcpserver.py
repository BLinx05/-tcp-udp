#!/usr/bin/env python3
"""
TCP Reverse Server
Receives variable-length text chunks from client, reverses each chunk,
and sends back the reversed text.
Supports multiple concurrent clients via threading.
"""

import socket
import struct
import threading
import sys
import os
from datetime import datetime

# --- Constants ---
TYPE_INITIALIZATION = 1
TYPE_AGREE = 2
TYPE_REVERSE_REQUEST = 3
TYPE_REVERSE_ANSWER = 4

LOG_FILE = "run_log.txt"
LOG_LOCK = threading.Lock()


def log_event(message: str):
    """Append a timestamped message to the shared log file (thread-safe)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    line = f"[{timestamp}] {message}"
    with LOG_LOCK:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from socket, blocking until all are received."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed by peer")
        data += chunk
    return data


def handle_client(conn: socket.socket, addr: tuple, server_port: int):
    """
    Handle a single client connection.
    Protocol:
      1. Receive Initialization (Type=1) -> extract N
      2. Send agree (Type=2)
      3. Loop N times: receive reverseRequest (Type=3), send reverseAnswer (Type=4)
    """
    client_ip, client_port = addr
    log_event(f"New connection from {client_ip}:{client_port}")

    try:
        # --- Step 1: Receive Initialization ---
        # Type(2B) + N(4B) = 6 bytes
        header = recv_exact(conn, 6)
        msg_type, N = struct.unpack("!HI", header)
        if msg_type != TYPE_INITIALIZATION:
            log_event(f"ERROR: Expected Initialization (Type=1), got Type={msg_type}")
            conn.close()
            return
        log_event(f"Server <- Client ({client_ip}:{client_port}): "
                   f"Initialization (Type=1), N={N}")

        # --- Step 2: Send agree ---
        agree_pkt = struct.pack("!H", TYPE_AGREE)
        conn.sendall(agree_pkt)
        log_event(f"Server -> Client ({client_ip}:{client_port}): "
                   f"agree (Type=2)")

        # --- Step 3: Process N reverse requests ---
        for i in range(N):
            # Receive reverseRequest: Type(2B) + Length(4B) = 6 bytes header
            req_header = recv_exact(conn, 6)
            req_type, data_len = struct.unpack("!HI", req_header)
            if req_type != TYPE_REVERSE_REQUEST:
                log_event(f"ERROR: Expected reverseRequest (Type=3), got Type={req_type}")
                conn.close()
                return

            # Receive Data
            data = recv_exact(conn, data_len)
            log_event(f"Server <- Client ({client_ip}:{client_port}): "
                       f"reverseRequest (Type=3), Length={data_len}, "
                       f"Block={i+1}/{N}")

            # Reverse the entire chunk byte-by-byte
            reversed_data = data[::-1]

            # Send reverseAnswer: Type(2B) + Length(4B) + reverseData
            ans_header = struct.pack("!HI", TYPE_REVERSE_ANSWER, len(reversed_data))
            conn.sendall(ans_header + reversed_data)
            log_event(f"Server -> Client ({client_ip}:{client_port}): "
                       f"reverseAnswer (Type=4), Length={len(reversed_data)}, "
                       f"Block={i+1}/{N}")

        log_event(f"Client {client_ip}:{client_port} finished successfully "
                   f"({N} blocks processed)")

    except ConnectionError as e:
        log_event(f"Connection error with {client_ip}:{client_port}: {e}")
    except Exception as e:
        log_event(f"Unexpected error with {client_ip}:{client_port}: {e}")
    finally:
        conn.close()
        log_event(f"Connection closed: {client_ip}:{client_port}")


def start_server(host: str = "0.0.0.0", port: int = 12345):
    """Start the TCP server, listening for client connections."""
    # Initialize log file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== TCP Reverse Server Log ===\n")
        f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Listening on {host}:{port}\n\n")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(10)  # Allow up to 10 pending connections
    log_event(f"Server started, listening on {host}:{port}")

    try:
        while True:
            conn, addr = server_sock.accept()
            # Handle each client in a new thread for concurrency
            t = threading.Thread(target=handle_client, args=(conn, addr, port),
                                 daemon=True)
            t.start()
    except KeyboardInterrupt:
        log_event("Server shutting down (KeyboardInterrupt)")
    finally:
        server_sock.close()


if __name__ == "__main__":
    # Usage: python reversetcpserver.py [port]
    # Default port: 12345
    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    else:
        port = 12345
    start_server(port=port)
