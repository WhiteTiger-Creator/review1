# TCP reassembly contract

## Flow key

Unidirectional key: `srcIPv4|dstIPv4|srcPort|dstPort` (dotted decimal IPs, decimal ports).

## Duplex bout

A bout pairs two unidirectional flows that are exact swaps of each other. The **client** side is the endpoint that transmitted a TCP SYN (flag `0x02`) first by arrival order. Bout id equals the PCAP basename without `.pcap`.

Each public/holdout PCAP contains exactly one bout.

## Sequence placement

1. Find the client SYN. Client initial sequence = SYN `seq`. First client data byte maps to stream offset `0` at sequence `syn_seq + 1`.
2. Find the server SYN-ACK (flags SYN|ACK). Server data starts at `synack_seq + 1` → offset `0` on the reverse stream.
3. Process every TCP segment for a unidirectional flow in **arrival order**.
4. For a segment with sequence `seq` and payload `P`:
   - stream offset `off = seq - data_origin` (signed 32-bit seq arithmetic wrapped into int64 relative to origin).
   - Skip segments with empty payload.
   - Ignore RST-only control with empty payload for byte placement; still count packets.
5. **Prefer-newest overlap:** write each payload byte into a sparse map `offset → byte`. Later arrivals overwrite earlier bytes at the same offset.
6. **Retransmit collapse:** when a segment's entire offset span already holds identical bytes, increment `retransmit_count` and skip rewriting. When any byte differs, treat as overlap rewrite (increment `overlap_byte_count` by differing bytes) and apply prefer-newest.
7. **Out-of-order:** a data segment whose lowest offset is strictly greater than the highest contiguous covered offset from 0 (before applying it) increments `out_of_order_count` once.
8. Emit reassembled payload as the contiguous byte run from offset `0` until the first uncovered gap (exclusive). Trailing gaps after the first hole are discarded from the payload but still counted in packet stats.

## Packet stats (per bout, both directions summed unless noted)

- `packet_count`: all TCP packets belonging to the bout.
- `payload_byte_count`: length of concatenated client then server reassembled payloads (`client_payload || server_payload`).
- Directional payloads stay separate for feature knitting but are concatenated for the digest payload hash.
