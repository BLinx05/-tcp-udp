#!/usr/bin/env python3
"""
TCP Reverse Client
Sends an ASCII file to the server in variable-length chunks.
Receives reversed chunks and writes the fully reversed output file.
Chunk sizes are randomly determined using a seed for reproducibility.

Usage:
    python reversetcpclient.py <serverIP> <serverPort> <Lmin> <Lmax> <input_file> [chunk_seed]

Example:
    python reversetcpclient.py 127.0.0.1 12345 50 100 sample_ascii.txt 42
"""

import socket
import struct
import random
import sys
import os
from datetime import datetime

# --- Constants ---
TYPE_INITIALIZATION = 1
TYPE_AGREE = 2
TYPE_REVERSE_REQUEST = 3
TYPE_REVERSE_ANSWER = 4

LOG_FILE = "run_log.txt"


def log_event(message: str):
    """Append a timestamped message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    line = f"[{timestamp}] {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from socket."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Server closed connection unexpectedly")
        data += chunk
    return data


def generate_chunk_sizes(file_size: int, Lmin: int, Lmax: int, seed: int) -> list:
    """
    Generate the list of chunk sizes for the file.

    Algorithm:
      - Seed the random number generator with the given seed.
      - For each chunk except the last: generate a random integer in [Lmin, Lmax].
      - The last chunk takes all remaining bytes (may be less than Lmin).
      - Returns the list of chunk sizes and the total block count N.

    This function is called BEFORE sending the Initialization message,
    so that N can be communicated to the server.
    """
    random.seed(seed)
    chunks = []
    remaining = file_size
    while remaining > 0:
        if remaining <= Lmax:
            # Last chunk: take whatever is left
            chunks.append(remaining)
            break
        else:
            # Generate random chunk size in [Lmin, Lmax]
            chunk_size = random.randint(Lmin, Lmax)
            chunks.append(chunk_size)
            remaining -= chunk_size
    return chunks


def run_client(server_ip: str, server_port: int, Lmin: int, Lmax: int,
               input_file: str, chunk_seed: int = 42):
    """Main client logic."""

    # --- Initialize log ---
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n=== TCP Reverse Client Log ===\n")
        f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Server: {server_ip}:{server_port}\n")
        f.write(f"Input file: {input_file}\n")
        f.write(f"Lmin={Lmin}, Lmax={Lmax}, seed={chunk_seed}\n\n")

    # --- Read input file ---
    if not os.path.exists(input_file):
        log_event(f"ERROR: Input file '{input_file}' not found")
        sys.exit(1)

    with open(input_file, "rb") as f:
        file_data = f.read()

    file_size = len(file_data)
    log_event(f"Read input file: {file_size} bytes")

    # --- Generate chunk sizes ---
    chunk_sizes = generate_chunk_sizes(file_size, Lmin, Lmax, chunk_seed)
    N = len(chunk_sizes)
    log_event(f"Chunk size sequence: {chunk_sizes}")
    log_event(f"Total blocks (N): {N}")

    # --- Verify chunk sizes sum to file size ---
    assert sum(chunk_sizes) == file_size, \
        f"Chunk sum {sum(chunk_sizes)} != file size {file_size}"

    # --- Connect to server ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)  # 10-second timeout for all operations
    try:
        print(f"Connecting to {server_ip}:{server_port} ...")
        sock.connect((server_ip, server_port))
        log_event(f"Connected to server {server_ip}:{server_port}")
    except socket.timeout:
        log_event(f"ERROR: Connection timed out. Is the server running on {server_ip}:{server_port}?")
        print(f"\nERROR: Connection timed out after 10 seconds.")
        print(f"Please make sure the server is running first:")
        print(f"  python reversetcpserver.py {server_port}")
        sock.close()
        sys.exit(1)
    except ConnectionRefusedError:
        log_event(f"ERROR: Connection refused by {server_ip}:{server_port}")
        print(f"\nERROR: Connection refused. Is the server running on {server_ip}:{server_port}?")
        print(f"Start the server first: python reversetcpserver.py {server_port}")
        sock.close()
        sys.exit(1)
    except Exception as e:
        log_event(f"ERROR: Failed to connect: {e}")
        print(f"\nERROR: Failed to connect to {server_ip}:{server_port}: {e}")
        sock.close()
        sys.exit(1)

    try:
        # --- Send Initialization (Type=1) ---
        init_pkt = struct.pack("!HI", TYPE_INITIALIZATION, N)
        sock.sendall(init_pkt)
        log_event(f"Client -> Server: Initialization (Type=1), N={N}")

        # --- Receive agree (Type=2) ---
        agree_header = recv_exact(sock, 2)
        agree_type = struct.unpack("!H", agree_header)[0]
        if agree_type != TYPE_AGREE:
            log_event(f"ERROR: Expected agree (Type=2), got Type={agree_type}")
            sys.exit(1)
        log_event(f"Client <- Server: agree (Type=2)")

        # --- Send chunks one by one, receive reversed data ---
        reversed_chunks = []
        offset = 0

        for i, chunk_size in enumerate(chunk_sizes):
            # Extract chunk data
            chunk_data = file_data[offset:offset + chunk_size]
            offset += chunk_size

            # Display what we're sending (first 40 chars if long)
            preview = chunk_data.decode("ascii", errors="replace")
            if len(preview) > 40:
                preview = preview[:40] + "..."

            # Send reverseRequest (Type=3)
            req_header = struct.pack("!HI", TYPE_REVERSE_REQUEST, chunk_size)
            sock.sendall(req_header + chunk_data)
            log_event(f"Client -> Server: reverseRequest (Type=3), "
                       f"Length={chunk_size}, Block={i+1}/{N}, "
                       f"Bytes=[{offset-chunk_size}..{offset-1}]")

            # Receive reverseAnswer (Type=4)
            ans_header = recv_exact(sock, 6)
            ans_type, ans_len = struct.unpack("!HI", ans_header)
            if ans_type != TYPE_REVERSE_ANSWER:
                log_event(f"ERROR: Expected reverseAnswer (Type=4), "
                           f"got Type={ans_type}")
                sys.exit(1)

            reversed_data = recv_exact(sock, ans_len)
            reversed_chunks.append(reversed_data)
            reversed_text = reversed_data.decode("ascii", errors="replace")
            log_event(f"Client <- Server: reverseAnswer (Type=4), "
                       f"Length={ans_len}, Block={i+1}/{N}")

            # Print the reversed chunk to terminal
            print(f"第{i+1}块：{reversed_text}")

        # --- Write output file (concatenated reversed chunks) ---
        output_file = os.path.splitext(input_file)[0] + "_reversed.txt"
        with open(output_file, "wb") as f:
            for chunk in reversed_chunks:
                f.write(chunk)
        log_event(f"\nReversed output written to: {output_file}")
        log_event(f"Total blocks processed: {N}, Total bytes: {file_size}")

    except socket.timeout:
        log_event("ERROR: Connection timed out")
    except ConnectionError as e:
        log_event(f"ERROR: {e}")
    except Exception as e:
        log_event(f"ERROR: Unexpected error: {e}")
    finally:
        sock.close()
        log_event("Connection closed")


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python reversetcpclient.py <serverIP> <serverPort> "
              "<Lmin> <Lmax> <input_file> [chunk_seed]")
        print("Example: python reversetcpclient.py 127.0.0.1 12345 50 100 "
              "sample_ascii.txt 42")
        sys.exit(1)

    server_ip = sys.argv[1]
    try:
        server_port = int(sys.argv[2])
    except ValueError:
        print(f"Invalid port number: {sys.argv[2]}")
        sys.exit(1)

    try:
        Lmin = int(sys.argv[3])
        Lmax = int(sys.argv[4])
    except ValueError:
        print(f"Invalid Lmin/Lmax values")
        sys.exit(1)

    if Lmin > Lmax:
        print("ERROR: Lmin must be <= Lmax")
        sys.exit(1)

    input_file = sys.argv[5]

    chunk_seed = 42  # default seed
    if len(sys.argv) >= 7:
        try:
            chunk_seed = int(sys.argv[6])
        except ValueError:
            print(f"Invalid seed value: {sys.argv[6]}")
            sys.exit(1)

    run_client(server_ip, server_port, Lmin, Lmax, input_file, chunk_seed)
