"""Authoring helper: synthesize public + hidden PCAP banks for cdnqual."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

ETH_IPV4 = b"\x08\x00"
FLAGS_SYN = 0x02
FLAGS_ACK = 0x10
FLAGS_SYNACK = 0x12
FLAGS_PSHACK = 0x18
FLAGS_FINACK = 0x11


def ip_bytes(dotted: str) -> bytes:
    return bytes(int(x) for x in dotted.split("."))


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def ipv4_tcp_frame(
    src: str,
    dst: str,
    sport: int,
    dport: int,
    seq: int,
    ack: int,
    flags: int,
    payload: bytes,
    ttl: int = 64,
) -> bytes:
    sip, dip = ip_bytes(src), ip_bytes(dst)
    tcp_off = 5
    tcp_len = tcp_off * 4 + len(payload)
    tcp_hdr = struct.pack(
        "!HHIIBBHHH",
        sport,
        dport,
        seq & 0xFFFFFFFF,
        ack & 0xFFFFFFFF,
        (tcp_off << 4) & 0xF0,
        flags & 0xFF,
        65535,
        0,
        0,
    )
    pseudo = sip + dip + struct.pack("!BBH", 0, 6, tcp_len) + tcp_hdr + payload
    tcsum = checksum(pseudo)
    tcp = tcp_hdr[:16] + struct.pack("!H", tcsum) + tcp_hdr[18:] + payload

    ihl = 5
    total = ihl * 4 + len(tcp)
    ip_hdr = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total,
        0x1234,
        0,
        ttl,
        6,
        0,
        sip,
        dip,
    )
    ip_c = checksum(ip_hdr)
    ip_hdr = ip_hdr[:10] + struct.pack("!H", ip_c) + ip_hdr[12:]
    eth = b"\xaa" * 6 + b"\xbb" * 6 + ETH_IPV4
    return eth + ip_hdr + tcp


def pcap_write(path: Path, packets: list[tuple[int, int, bytes]]) -> None:
    out = bytearray()
    out += struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for ts_sec, ts_usec, body in packets:
        out += struct.pack("<IIII", ts_sec, ts_usec, len(body), len(body))
        out += body
    path.write_bytes(out)


def bout_clean(path: Path) -> None:
    c, s = "10.0.0.1", "10.0.0.2"
    cp, sp = 40000, 443
    cseq, sseq = 1000, 5000
    pkts = [
        (1, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (1, 1000, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (1, 2000, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (1, 3000, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"PING")),
        (1, 4000, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 5, FLAGS_PSHACK, b"PONG")),
        (1, 5000, ipv4_tcp_frame(c, s, cp, sp, cseq + 5, sseq + 5, FLAGS_FINACK, b"")),
        (1, 6000, ipv4_tcp_frame(s, c, sp, cp, sseq + 5, cseq + 6, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def bout_ooo(path: Path) -> None:
    c, s = "10.1.0.1", "10.1.0.2"
    cp, sp = 41000, 80
    cseq, sseq = 2000, 8000
    # client data "ABCDEFGH" sent as two segments; second arrives before first
    pkts = [
        (2, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (2, 500, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (2, 1000, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (2, 2000, ipv4_tcp_frame(c, s, cp, sp, cseq + 5, sseq + 1, FLAGS_PSHACK, b"EFGH")),  # OOO
        (2, 3000, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"ABCD")),
        (2, 4000, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 9, FLAGS_PSHACK, b"OK")),
        (2, 5000, ipv4_tcp_frame(c, s, cp, sp, cseq + 9, sseq + 3, FLAGS_FINACK, b"")),
        (2, 6000, ipv4_tcp_frame(s, c, sp, cp, sseq + 3, cseq + 10, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def bout_rexmit(path: Path) -> None:
    c, s = "10.2.0.1", "10.2.0.2"
    cp, sp = 42000, 8080
    cseq, sseq = 3000, 9000
    pkts = [
        (3, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (3, 400, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (3, 800, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (3, 1200, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"HELLO")),
        (3, 1600, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"HELLO")),  # identical rexmit
        (3, 2000, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 6, FLAGS_PSHACK, b"WORLD")),
        (3, 2400, ipv4_tcp_frame(c, s, cp, sp, cseq + 6, sseq + 6, FLAGS_FINACK, b"")),
        (3, 2800, ipv4_tcp_frame(s, c, sp, cp, sseq + 6, cseq + 7, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def bout_overlap(path: Path) -> None:
    c, s = "10.3.0.1", "10.3.0.2"
    cp, sp = 43000, 8443
    cseq, sseq = 4000, 10000
    # first write "AAAA", later overlapping rewrite "XX" at offset 1 → "AXXA"
    pkts = [
        (4, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (4, 300, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (4, 600, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (4, 900, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"AAAA")),
        (4, 1200, ipv4_tcp_frame(c, s, cp, sp, cseq + 2, sseq + 1, FLAGS_PSHACK, b"XX")),  # overlap newest
        (4, 1500, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 5, FLAGS_PSHACK, b"ZZ")),
        (4, 1800, ipv4_tcp_frame(c, s, cp, sp, cseq + 5, sseq + 3, FLAGS_FINACK, b"")),
        (4, 2100, ipv4_tcp_frame(s, c, sp, cp, sseq + 3, cseq + 6, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def bout_gap(path: Path) -> None:
    c, s = "10.4.0.1", "10.4.0.2"
    cp, sp = 44000, 9000
    cseq, sseq = 5000, 11000
    # missing middle segment → payload stops at first gap ("12" only; "56" after gap discarded)
    pkts = [
        (5, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (5, 200, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (5, 400, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (5, 600, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, b"12")),
        (5, 800, ipv4_tcp_frame(c, s, cp, sp, cseq + 5, sseq + 1, FLAGS_PSHACK, b"56")),  # gap at 2..4
        (5, 1000, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 7, FLAGS_PSHACK, b"OK")),
        (5, 1200, ipv4_tcp_frame(c, s, cp, sp, cseq + 7, sseq + 3, FLAGS_FINACK, b"")),
        (5, 1400, ipv4_tcp_frame(s, c, sp, cp, sseq + 3, cseq + 8, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def bout_long(path: Path) -> None:
    c, s = "10.5.0.1", "10.5.0.2"
    cp, sp = 45000, 443
    cseq, sseq = 6000, 12000
    payload = bytes(range(64))
    pkts = [
        (6, 0, ipv4_tcp_frame(c, s, cp, sp, cseq, 0, FLAGS_SYN, b"")),
        (6, 100, ipv4_tcp_frame(s, c, sp, cp, sseq, cseq + 1, FLAGS_SYNACK, b"")),
        (6, 200, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_ACK, b"")),
        (6, 300, ipv4_tcp_frame(c, s, cp, sp, cseq + 1, sseq + 1, FLAGS_PSHACK, payload[:32])),
        (6, 400, ipv4_tcp_frame(c, s, cp, sp, cseq + 33, sseq + 1, FLAGS_PSHACK, payload[32:])),
        (6, 500, ipv4_tcp_frame(s, c, sp, cp, sseq + 1, cseq + 65, FLAGS_PSHACK, b"ACKDATA")),
        (6, 600, ipv4_tcp_frame(c, s, cp, sp, cseq + 65, sseq + 8, FLAGS_FINACK, b"")),
        (6, 700, ipv4_tcp_frame(s, c, sp, cp, sseq + 8, cseq + 66, FLAGS_FINACK, b"")),
    ]
    pcap_write(path, pkts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", type=Path, required=True)
    ap.add_argument("--hidden", type=Path, required=True)
    ap.add_argument("--public-labels", type=Path, required=True)
    ap.add_argument("--hidden-labels", type=Path, required=True)
    args = ap.parse_args()
    args.public.mkdir(parents=True, exist_ok=True)
    args.hidden.mkdir(parents=True, exist_ok=True)
    args.public_labels.parent.mkdir(parents=True, exist_ok=True)
    args.hidden_labels.parent.mkdir(parents=True, exist_ok=True)

    public = {
        "bout_clean": bout_clean,
        "bout_ooo": bout_ooo,
        "bout_rexmit": bout_rexmit,
        "bout_overlap": bout_overlap,
        "bout_gap": bout_gap,
        "bout_long": bout_long,
    }
    # Labels chosen so ridge has a learnable signal: messy sessions → 0, clean/long → 1
    public_y = {
        "bout_clean": 1,
        "bout_ooo": 0,
        "bout_rexmit": 0,
        "bout_overlap": 0,
        "bout_gap": 0,
        "bout_long": 1,
    }
    for name, fn in public.items():
        fn(args.public / f"{name}.pcap")
    args.public_labels.write_text(
        "".join(f'{{"bout_id":"{k}","y":{public_y[k]}}}\n' for k in sorted(public_y))
    )

    hidden = {
        "hz_alpha": bout_clean,
        "hz_bravo": bout_ooo,
        "hz_charlie": bout_rexmit,
        "hz_delta": bout_overlap,
    }
    # Remap endpoints inside copies by regenerating with same helpers but different filenames
    for name, fn in hidden.items():
        fn(args.hidden / f"{name}.pcap")
    hidden_y = {"hz_alpha": 1, "hz_bravo": 0, "hz_charlie": 0, "hz_delta": 0}
    args.hidden_labels.write_text(
        "".join(f'{{"bout_id":"{k}","y":{hidden_y[k]}}}\n' for k in sorted(hidden_y))
    )
    print("generated", len(public), "public and", len(hidden), "hidden pcaps")


if __name__ == "__main__":
    main()
