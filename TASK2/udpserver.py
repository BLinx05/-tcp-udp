#!/usr/bin/env python3
"""
UDP Reliable Transfer Server
Simulates TCP-like connection establishment and reliable data transfer over UDP.

Features:
  - Three-way handshake with StudentID validation
  - Random packet drop to simulate unreliable UDP
  - Cumulative acknowledgment (GBN receiver)
  - Logs all events with timestamps

Usage:
    python udpserver.py [port] [drop_rate]
    Default port: 12346
    Default drop_rate: 0.2 (20% packet drop probability)
"""

7import socket
import struct
import random
import sys
from datetime import datetime

# --- Protocol Constants ---
FLAG_SYN  = 0x0001
FLAG_ACK  = 0x0002
FLAG_FIN  = 0x0004
FLAG_DATA = 0x0008

STUDENT_ID_XOR_KEY = 0x5A3C

HEADER_FORMAT = "!HHIIHHH"  # src_port, dst_port, seq, ack, flags, student_id, data_len
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 18 bytes

LOG_FILE = "run_log.txt"


def log_event(message: str):
    """Append a timestamped message to the log file and print it."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    line = f"[{timestamp}] {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def build_packet(src_port: int, dst_port: int, seq: int, ack: int,
                 flags: int, student_id: int, data: bytes = b"") -> bytes:
    """Build a UDP packet with the custom header + optional data."""
    header = struct.pack(HEADER_FORMAT, src_port, dst_port, seq, ack,
                         flags, student_id, len(data))
    return header + data


def unpack_packet(packet: bytes) -> dict:
    """Parse a received UDP packet. Returns dict with fields or None if invalid."""
    if len(packet) < HEADER_SIZE:
        return None
    src_port, dst_port, seq, ack, flags, student_id, data_len = \
        struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    data = packet[HEADER_SIZE:HEADER_SIZE + data_len]
    return {
        "src_port": src_port,
        "dst_port": dst_port,
        "seq": seq,
        "ack": ack,
        "flags": flags,
        "student_id": student_id,
        "data_len": data_len,
        "data": data,
    }


def validate_student_id(received_value: int) -> bool:
    """
    Validate the StudentID field: XOR with 0x5A3C and check if the
    result is a valid 4-digit integer (0-9999).
    """
    original = received_value ^ STUDENT_ID_XOR_KEY
    return 0 <= original <= 9999


def run_server(port: int = 12346, drop_rate: float = 0.2):
    """Main server loop."""

    # Initialize log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== UDP Reliable Transfer Server Log ===\n")
        f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Listening on port: {port}\n")
        f.write(f"Drop rate: {drop_rate*100:.0f}%\n\n")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind(("0.0.0.0", port))
    log_event(f"UDP Server started on port {port}")

    # We track each client's state by (ip, port) tuple
    # State: 'init' -> 'connected' -> 'transferring' -> 'done'
    client_states = {}

    try:
        while True:
            packet, client_addr = server_sock.recvfrom(4096)
            now = datetime.now()
            client_key = client_addr

            parsed = unpack_packet(packet)
            if parsed is None:
                log_event(f"Invalid packet from {client_addr}: too short")
                continue

            flags = parsed["flags"]
            seq = parsed["seq"]
            ack = parsed["ack"]
            student_id = parsed["student_id"]
            data = parsed["data"]
            src_port = parsed["src_port"]

            # --- Handle SYN (Connection Request) ---
            if flags & FLAG_SYN and not flags & FLAG_ACK:
                log_event(f"Server <- {client_addr}: SYN, Seq={seq}, "
                           f"StudentID={student_id} (0x{student_id:04X})")

                if not validate_student_id(student_id):
                    extracted = student_id ^ STUDENT_ID_XOR_KEY
                    log_event(f"Server -> {client_addr}: REJECTED - "
                               f"Invalid StudentID: XOR result={extracted} "
                               f"(expected 0-9999)")
                    continue

                original_sid = student_id ^ STUDENT_ID_XOR_KEY
                log_event(f"Server: StudentID valid (original={original_sid})")

                # Send SYN+ACK
                server_seq = random.randint(1000, 9999)
                synack = build_packet(
                    src_port=port, dst_port=client_addr[1],
                    seq=server_seq, ack=seq + 1,
                    flags=FLAG_SYN | FLAG_ACK, student_id=0
                )
                server_sock.sendto(synack, client_addr)
                log_event(f"Server -> {client_addr}: SYN+ACK, "
                           f"Seq={server_seq}, Ack={seq+1}")

                client_states[client_key] = {
                    "state": "awaiting_ack",
                    "server_seq": server_seq,
                    "client_seq": seq,
                    "next_expected": 0,  # First data packet seq
                }

            # --- Handle ACK (completing handshake) ---
            elif (flags & FLAG_ACK) and \
                 client_key in client_states and \
                 client_states[client_key]["state"] == "awaiting_ack":
                log_event(f"Server <- {client_addr}: ACK, "
                           f"Seq={seq}, Ack={ack} (Handshake complete)")
                client_states[client_key]["state"] = "transferring"
                log_event(f"Server: Connection established with {client_addr}, "
                           f"ready to receive data")

            # --- Handle DATA ---
            elif flags & FLAG_DATA:
                state = client_states.get(client_key)
                valid_states = ("transferring", "awaiting_ack", "connected")
                if state is None or state["state"] not in valid_states:
                    log_event(f"Server: DATA from {client_addr} but not connected, ignoring")
                    continue

                # Update state to transferring if needed
                if state["state"] != "transferring":
                    state["state"] = "transferring"

                # Random drop simulation
                if random.random() < drop_rate:
                    log_event(f"Server <- {client_addr}: DATA Seq={seq}, "
                               f"Len={parsed['data_len']} -- [SIMULATED DROP]")
                    continue  # Don't send ACK, simulating loss

                next_expected = state["next_expected"]

                log_event(f"Server <- {client_addr}: DATA Seq={seq}, "
                           f"Len={parsed['data_len']}")

                # Cumulative ACK: only advance if this is the expected packet
                if seq == next_expected:
                    state["next_expected"] = seq + 1
                    log_event(f"Server: Cumulative ACK updated to {seq + 1}")
                else:
                    log_event(f"Server: Out-of-order packet (got {seq}, "
                               f"expected {next_expected}), sending ACK={next_expected}")

                # Send ACK with cumulative acknowledgment
                # Include server system time in the ACK data field
                server_time_str = datetime.now().strftime("%H:%M:%S")
                server_time_bytes = server_time_str.encode("ascii")
                ack_pkt = build_packet(
                    src_port=port, dst_port=client_addr[1],
                    seq=0, ack=state["next_expected"],
                    flags=FLAG_ACK, student_id=0,
                    data=server_time_bytes
                )
                server_sock.sendto(ack_pkt, client_addr)
                log_event(f"Server -> {client_addr}: ACK, "
                           f"AckNum={state['next_expected']}, "
                           f"ServerTime={server_time_str}")

            # --- Handle FIN ---
            elif flags & FLAG_FIN:
                if client_key in client_states:
                    log_event(f"Server <- {client_addr}: FIN, Seq={seq}")
                    # Send FIN+ACK
                    finack = build_packet(
                        src_port=port, dst_port=client_addr[1],
                        seq=0, ack=seq + 1,
                        flags=FLAG_FIN | FLAG_ACK, student_id=0
                    )
                    server_sock.sendto(finack, client_addr)
                    log_event(f"Server -> {client_addr}: FIN+ACK")
                    del client_states[client_key]

    except KeyboardInterrupt:
        log_event("Server shutting down (KeyboardInterrupt)")
    finally:
        server_sock.close()


if __name__ == "__main__":
    port = 12346
    drop_rate = 0.2

    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)

    if len(sys.argv) >= 3:
        try:
            drop_rate = float(sys.argv[2])
            if not 0 <= drop_rate <= 1:
                raise ValueError
        except ValueError:
            print(f"Invalid drop rate: {sys.argv[2]} (must be 0.0-1.0)")
            sys.exit(1)

    run_server(port, drop_rate)
