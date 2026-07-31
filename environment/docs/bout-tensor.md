# Session feature contract

Each bout emits one JSONL object with keys `bout_id` and `x` (length-12 integer vector).

Index map (all integers; no floats in the tensor):

| i | Name | Definition |
|---|------|------------|
| 0 | `payload_byte_count` | `len(client_payload) + len(server_payload)` |
| 1 | `packet_count` | TCP packets in the bout |
| 2 | `retransmit_count` | sum of unidirectional retransmit collapses |
| 3 | `out_of_order_count` | sum of unidirectional OOO increments |
| 4 | `overlap_byte_count` | sum of differing overwritten bytes |
| 5 | `duration_us` | `(last_ts_usec_total) - (first_ts_usec_total)` where `ts_usec_total = ts_sec*1_000_000 + ts_usec` |
| 6 | `avg_payload_len_milli` | `1000 * payload_byte_count / max(packet_count, 1)` |
| 7 | `syn_ack_rtt_us` | server SYN-ACK arrival − client SYN arrival (µs); `0` if either missing |
| 8 | `fin_seen` | `1` if any FIN flag observed in the bout else `0` |
| 9 | `payload_entropy_milli` | Shannon entropy of concatenated payloads over byte alphabet, scaled by 1000 and floored to int (`0` if empty). Formula: `-1000 * Σ p_b * log2(p_b)` then floor. |
| 10 | `unique_seq_span` | `(max_written_offset+1)` summed across both directions for offsets that received at least one write (before gap trim) |
| 11 | `direction_asym_milli` | `1000 * len(client_payload) / max(payload_byte_count, 1)` |

Feature rows must be emitted in ascending `bout_id` lexicographic order.
