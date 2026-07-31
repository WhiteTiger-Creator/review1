# PCAP wire contract

## Global header (24 bytes, little-endian)

| Offset | Size | Value |
|--------|------|-------|
| 0 | 4 | magic `0xa1b2c3d4` |
| 4 | 2 | major `2` |
| 6 | 2 | minor `4` |
| 8 | 4 | thiszone `0` |
| 12 | 4 | sigfigs `0` |
| 16 | 4 | snaplen `65535` |
| 20 | 4 | network `1` (Ethernet) |

## Per-packet record

| Field | Size | Notes |
|-------|------|-------|
| ts_sec | 4 | capture time seconds |
| ts_usec | 4 | capture time microseconds |
| incl_len | 4 | bytes captured |
| orig_len | 4 | bytes on wire |
| body | incl_len | link-layer frame |

## Frame layout

- Ethernet: 14 bytes. Ethertype must be `0x0800` (IPv4). Other ethertypes are ignored.
- IPv4: IHL ≥ 5. Protocol must be `6` (TCP). Ignore fragments (`MF` set or non-zero fragment offset).
- TCP: data offset ≥ 5. Payload = bytes after TCP header through end of IP payload.

Packet arrival order is the order frames appear in the PCAP file (not sequence number order).
