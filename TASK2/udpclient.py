#!/usr/bin/env python3
"""
UDP Reliable Transfer Client with GBN Protocol
Simulates TCP-like connection establishment and Go-Back-N reliable data
transfer over UDP.

Features:
  - Three-way handshake with StudentID field
  - GBN sliding window protocol (400-byte window)
  - Variable packet sizes (40-80 bytes)
  - Timeout-based retransmission
  - RTT calculation and statistics via pandas
  - Comprehensive logging

Usage:
    python udpclient.py <serverIP> <serverPort> [student_id_last4] [timeout_ms]

Example:
    python udpclient.py 127.0.0.1 12346 1234 300
"""

import socket
import struct
import random
import sys
import time
from datetime import datetime
import pandas as pd

# --- Protocol Constants ---
FLAG_SYN  = 0x0001
FLAG_ACK  = 0x0002
FLAG_FIN  = 0x0004
FLAG_DATA = 0x0008

STUDENT_ID_XOR_KEY = 0x5A3C

HEADER_FORMAT = "!HHIIHHH"  # src_port, dst_port, seq, ack, flags, student_id, data_len
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 18 bytes

WINDOW_SIZE_BYTES = 400      # Fixed send window in bytes
PKT_MIN_SIZE = 40            # Minimum data per packet
PKT_MAX_SIZE = 80            # Maximum data per packet
TOTAL_PACKETS = 30           # Total number of data packets to send

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


def compute_student_id_field(last4: int) -> int:
    """Compute the StudentID field value: last4 XOR 0x5A3C."""
    return (last4 & 0xFFFF) ^ STUDENT_ID_XOR_KEY


def generate_packet_sizes(n: int, min_size: int, max_size: int,
                          seed: int = 123) -> list:
    """
    Generate n random packet sizes between min_size and max_size.
    Uses a fixed seed for reproducibility.
    """
    random.seed(seed)
    return [random.randint(min_size, max_size) for _ in range(n)]


def generate_text_data(total_bytes: int) -> bytes:
    """
    Generate ASCII text data of the specified total size.
    Uses a repeating pattern of interesting English text.
    """
    base_text = (
        "The quick brown fox jumps over the lazy dog. "
        "Computer networking is the backbone of modern communication. "
        "UDP is connectionless but we can build reliability on top. "
        "Go-Back-N protocol uses cumulative acknowledgments. "
        "Sliding window flow control prevents overwhelming the receiver. "
        "Packet loss is simulated by randomly dropping datagrams. "
        "Timeout and retransmission ensure reliable data delivery. "
        "Round-trip time measurement helps optimize performance. "
    )
    base_bytes = base_text.encode("ascii")
    repeats = (total_bytes // len(base_bytes)) + 1
    data = (base_bytes * repeats)[:total_bytes]
    return data


def compute_timeout(rtt_list: list, default_ms: float = 300.0) -> float:
    """
    Compute adaptive timeout based on RTT history.
    Uses: avg_RTT + 4 * std_dev, clamped to [default_ms, 5000ms].
    If not enough samples, returns default_ms.
    """
    if len(rtt_list) < 3:
        return default_ms / 1000.0  # Convert to seconds

    rtt_series = pd.Series(rtt_list)
    avg_rtt = rtt_series.mean()
    std_rtt = rtt_series.std()
    if pd.isna(std_rtt):
        std_rtt = 0

    # Similar to TCP: EstimatedRTT + 4 * DevRTT
    timeout_ms = avg_rtt + 4 * std_rtt
    timeout_ms = max(default_ms, min(timeout_ms, 5000.0))
    return timeout_ms / 1000.0  # Convert to seconds


def run_client(server_ip: str, server_port: int, student_id_last4: int = 1234,
               initial_timeout_ms: float = 300.0):
    """Main client logic."""

    # Initialize log
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n=== UDP Reliable Transfer Client Log ===\n")
        f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Server: {server_ip}:{server_port}\n")
        f.write(f"StudentID last4: {student_id_last4}\n")
        f.write(f"Initial timeout: {initial_timeout_ms}ms\n")
        f.write(f"Window size: {WINDOW_SIZE_BYTES} bytes\n")
        f.write(f"Total packets: {TOTAL_PACKETS}\n\n")

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.bind(("0.0.0.0", 0))  # Bind to any available port
    client_sock.settimeout(initial_timeout_ms / 1000.0)
    client_port = client_sock.getsockname()[1]
    server_addr = (server_ip, server_port)

    student_id_field = compute_student_id_field(student_id_last4)
    log_event(f"Computed StudentID field: {student_id_field} "
              f"(0x{student_id_field:04X}) = "
              f"{student_id_last4} XOR 0x{STUDENT_ID_XOR_KEY:04X}")

    # ============ Phase 1: Three-Way Handshake ============
    log_event("\n--- Three-Way Handshake ---")

    # Step 1: Send SYN
    client_seq = random.randint(1000, 9999)
    syn_pkt = build_packet(
        src_port=client_port, dst_port=server_port,
        seq=client_seq, ack=0,
        flags=FLAG_SYN, student_id=student_id_field
    )
    client_sock.sendto(syn_pkt, server_addr)
    log_event(f"Client -> Server: SYN, Seq={client_seq}, "
               f"StudentID={student_id_field}")

    # Step 2: Receive SYN+ACK
    try:
        response, _ = client_sock.recvfrom(4096)
    except socket.timeout:
        log_event("ERROR: No response to SYN (timeout)")
        client_sock.close()
        sys.exit(1)

    synack = unpack_packet(response)
    if synack is None or not (synack["flags"] & FLAG_SYN and synack["flags"] & FLAG_ACK):
        log_event(f"ERROR: Expected SYN+ACK, got flags=0x{synack['flags']:04X}")
        client_sock.close()
        sys.exit(1)

    server_seq = synack["seq"]
    log_event(f"Client <- Server: SYN+ACK, Seq={server_seq}, "
               f"Ack={synack['ack']}")

    # Step 3: Send ACK
    ack_pkt = build_packet(
        src_port=client_port, dst_port=server_port,
        seq=client_seq + 1, ack=server_seq + 1,
        flags=FLAG_ACK, student_id=0
    )
    client_sock.sendto(ack_pkt, server_addr)
    log_event(f"Client -> Server: ACK, Seq={client_seq+1}, "
               f"Ack={server_seq+1}")
    log_event("Handshake complete. Connection established.\n")

    # ============ Phase 2: Data Transfer (GBN Protocol) ============
    log_event("--- Data Transfer (GBN) ---")

    # Generate packet sizes and text data
    packet_sizes = generate_packet_sizes(TOTAL_PACKETS, PKT_MIN_SIZE, PKT_MAX_SIZE)
    total_bytes = sum(packet_sizes)
    text_data = generate_text_data(total_bytes)

    log_event(f"Generated {TOTAL_PACKETS} packet sizes: {packet_sizes}")
    log_event(f"Total data to send: {total_bytes} bytes")

    # Build packet data slices
    # packet_data[i] = bytes for packet i
    packet_data = []
    offset = 0
    for sz in packet_sizes:
        packet_data.append(text_data[offset:offset + sz])
        offset += sz

    # GBN State
    base = 0           # First unacknowledged packet
    next_seq = 0       # Next packet to send
    acked = set()      # Set of acknowledged sequence numbers
    send_times = {}    # seq -> send time (for RTT calculation)
    rtt_values = []    # List of successful RTT values (in ms)
    total_sends = 0    # Total number of sends (including retransmissions)
    total_retrans = 0  # Total number of retransmissions
    consecutive_timeouts = 0  # Consecutive timeouts (for dead-server detection)
    MAX_CONSECUTIVE_TIMEOUTS = 15

    current_timeout = initial_timeout_ms / 1000.0

    while base < TOTAL_PACKETS:
        # Send all packets that fit within the window
        bytes_in_flight = 0
        for s in range(base, next_seq):
            if s not in acked:
                bytes_in_flight += packet_sizes[s]

        while next_seq < TOTAL_PACKETS:
            new_bytes = bytes_in_flight + packet_sizes[next_seq]
            if new_bytes <= WINDOW_SIZE_BYTES:
                # Send this packet
                pkt = build_packet(
                    src_port=client_port, dst_port=server_port,
                    seq=next_seq, ack=0,
                    flags=FLAG_DATA, student_id=0,
                    data=packet_data[next_seq]
                )
                client_sock.sendto(pkt, server_addr)
                now = time.time()
                if next_seq not in send_times:
                    send_times[next_seq] = now
                else:
                    # Retransmission
                    total_retrans += 1

                # Calculate byte range for this packet
                byte_start = sum(packet_sizes[:next_seq])
                byte_end = byte_start + packet_sizes[next_seq] - 1

                if next_seq in acked:
                    log_event(f"Client -> Server: DATA Seq={next_seq}, "
                               f"Bytes=[{byte_start}..{byte_end}], "
                               f"Len={packet_sizes[next_seq]} -- "
                               f"重传第{next_seq+1}个（第{byte_start}~{byte_end}字节）数据包")
                else:
                    log_event(f"Client -> Server: DATA Seq={next_seq}, "
                               f"Bytes=[{byte_start}..{byte_end}], "
                               f"Len={packet_sizes[next_seq]}")
                    print(f"第{next_seq+1}个（第{byte_start}~{byte_end}字节）"
                          f"client端已经发送")

                total_sends += 1
                bytes_in_flight = new_bytes
                next_seq += 1
            else:
                break  # Window is full

        # Wait for ACK
        client_sock.settimeout(current_timeout)
        try:
            response, _ = client_sock.recvfrom(4096)
            now = time.time()

            ack_parsed = unpack_packet(response)
            if ack_parsed is None:
                continue

            if ack_parsed["flags"] & FLAG_ACK:
                ack_num = ack_parsed["ack"]
                # Extract server system time from ACK data
                server_time_str = ""
                if ack_parsed["data"]:
                    try:
                        server_time_str = ack_parsed["data"].decode("ascii")
                    except:
                        server_time_str = "unknown"
                log_event(f"Client <- Server: ACK, AckNum={ack_num} "
                           f"(cumulative, base was {base}), "
                           f"ServerTime={server_time_str}")

                if ack_num > base:
                    consecutive_timeouts = 0  # Reset timeout counter on progress
                    # Cumulative ACK: all packets < ack_num are acknowledged
                    for s in range(base, ack_num):
                        if s not in acked and s in send_times:
                            rtt_ms = (now - send_times[s]) * 1000.0
                            rtt_values.append(rtt_ms)

                            byte_start = sum(packet_sizes[:s])
                            byte_end = byte_start + packet_sizes[s] - 1
                            log_event(f"  Packet {s} ACKed: RTT={rtt_ms:.2f}ms")
                            print(f"第{s+1}个（第{byte_start}~{byte_end}字节）"
                                  f"server端已经收到，"
                                  f"RTT是{rtt_ms:.2f}ms，"
                                  f"server系统时间={server_time_str}")
                        acked.add(s)
                    base = ack_num

                    # Update adaptive timeout
                    if len(rtt_values) >= 3:
                        current_timeout = compute_timeout(
                            rtt_values, initial_timeout_ms)
                        # Don't log every update to avoid noise
                        # log_event(f"Adaptive timeout updated: "
                        #           f"{current_timeout*1000:.1f}ms")

        except socket.timeout:
            consecutive_timeouts += 1
            # Timeout! Retransmit all unacked packets from base to next_seq-1
            log_event(f"--- TIMEOUT ({current_timeout*1000:.0f}ms, "
                       f"consecutive={consecutive_timeouts}) --- "
                       f"Retransmitting packets {base} to {next_seq-1}")

            if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                log_event(f"ERROR: {MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts. "
                           f"Server appears to be down. Aborting.")
                print(f"\nERROR: {MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts. "
                      f"Server may have stopped. Exiting.")
                client_sock.close()
                sys.exit(1)

            for s in range(base, next_seq):
                pkt = build_packet(
                    src_port=client_port, dst_port=server_port,
                    seq=s, ack=0,
                    flags=FLAG_DATA, student_id=0,
                    data=packet_data[s]
                )
                client_sock.sendto(pkt, server_addr)
                send_times[s] = time.time()  # Update send time
                total_sends += 1
                total_retrans += 1

                byte_start = sum(packet_sizes[:s])
                byte_end = byte_start + packet_sizes[s] - 1
                log_event(f"Client -> Server: DATA Seq={s}, "
                           f"Bytes=[{byte_start}..{byte_end}] -- RETRANSMIT")
                print(f"重传第{s+1}个（第{byte_start}~{byte_end}字节）数据包")

    # All packets acknowledged
    log_event("\nAll 30 packets acknowledged by server!")

    # ============ Phase 3: Connection Termination ============
    log_event("\n--- Connection Termination ---")

    # Send FIN
    fin_pkt = build_packet(
        src_port=client_port, dst_port=server_port,
        seq=client_seq + 2, ack=0,
        flags=FLAG_FIN, student_id=0
    )
    client_sock.sendto(fin_pkt, server_addr)
    log_event(f"Client -> Server: FIN, Seq={client_seq+2}")

    # Wait for FIN+ACK
    client_sock.settimeout(3.0)
    try:
        response, _ = client_sock.recvfrom(4096)
        finack = unpack_packet(response)
        if finack and finack["flags"] & FLAG_FIN and finack["flags"] & FLAG_ACK:
            log_event(f"Client <- Server: FIN+ACK (connection closed)")
    except socket.timeout:
        log_event("No FIN+ACK received (timeout), closing anyway")

    client_sock.close()

    # ============ Statistics Summary ============
    log_event("\n========== 汇总统计 ==========")
    log_event(f"总发包次数（含重传）: {total_sends}")
    log_event(f"重传次数: {total_retrans}")
    log_event(f"成功接收的ACK数: {len(rtt_values)}")

    # Packet loss rate per spec: TOTAL_PACKETS / total_sends * 100%
    if total_sends > 0:
        loss_rate = (TOTAL_PACKETS / total_sends) * 100
    else:
        loss_rate = 0.0

    log_event(f"\n丢包率: {loss_rate:.2f}%  "
               f"({TOTAL_PACKETS}个唯一包 / {total_sends}次总发送)")

    if rtt_values:
        rtt_series = pd.Series(rtt_values)
        max_rtt = rtt_series.max()
        min_rtt = rtt_series.min()
        avg_rtt = rtt_series.mean()
        std_rtt = rtt_series.std()

        print(f"\n========== 汇总统计 ==========")
        print(f"丢包率: {loss_rate:.2f}%")
        print(f"最大RTT: {max_rtt:.2f} ms")
        print(f"最小RTT: {min_rtt:.2f} ms")
        print(f"平均RTT: {avg_rtt:.2f} ms")
        print(f"RTT标准差: {std_rtt:.2f} ms")

        log_event(f"最大RTT: {max_rtt:.2f} ms")
        log_event(f"最小RTT: {min_rtt:.2f} ms")
        log_event(f"平均RTT: {avg_rtt:.2f} ms")
        log_event(f"RTT标准差: {std_rtt:.2f} ms")
    else:
        log_event("No RTT values collected (all packets lost?)")

    log_event("\nClient finished.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python udpclient.py <serverIP> <serverPort> "
              "[student_id_last4] [timeout_ms]")
        print("Example: python udpclient.py 127.0.0.1 12346 1234 300")
        sys.exit(1)

    server_ip = sys.argv[1]
    try:
        server_port = int(sys.argv[2])
    except ValueError:
        print(f"Invalid port: {sys.argv[2]}")
        sys.exit(1)

    student_id_last4 = 1234
    if len(sys.argv) >= 4:
        try:
            student_id_last4 = int(sys.argv[3])
            if not 0 <= student_id_last4 <= 9999:
                raise ValueError
        except ValueError:
            print(f"Invalid student ID (must be 0-9999): {sys.argv[3]}")
            sys.exit(1)

    timeout_ms = 300.0
    if len(sys.argv) >= 5:
        try:
            timeout_ms = float(sys.argv[4])
            if timeout_ms <= 0:
                raise ValueError
        except ValueError:
            print(f"Invalid timeout: {sys.argv[4]}")
            sys.exit(1)

    run_client(server_ip, server_port, student_id_last4, timeout_ms)
