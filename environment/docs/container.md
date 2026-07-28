Little-endian PMW2 digitizer container for calorimeter lanes.

# PMW2 acquisition container

PMW2 is the on-disk format written by the test-stand digitizer crate. A shard is a
fixed-size file header followed by `frame_count` frames laid out back to back. Every
field is little-endian. There is no padding between fields, between headers and
payloads, or between frames.

## File header — 24 bytes

| Offset | Size | Type | Field | Rule |
|---|---|---|---|---|
| 0 | 4 | bytes | `magic` | ASCII `PMW2` |
| 4 | 2 | uint16 | `version` | must be `2` |
| 6 | 2 | uint16 | `header_bytes` | must be `24` (`FILE_HEADER_BYTES`) |
| 8 | 4 | uint32 | `run_id` | acquisition run identifier |
| 12 | 2 | uint16 | `shard_index` | crate-assigned shard ordinal, primary merge priority |
| 14 | 2 | uint16 | `adc_bits` | must be `12` or `14` |
| 16 | 4 | uint32 | `frame_count` | number of frames that follow; `0` is legal |
| 20 | 4 | uint32 | `reserved` | must be `0` |

`adc_bits` is a property of the shard, not of the frame: every frame in the file is
digitized at that width.

## Frame header — 28 bytes

| Offset | Size | Type | Field | Rule |
|---|---|---|---|---|
| 0 | 2 | uint16 | `lane_id` | readout lane |
| 2 | 2 | uint16 | `kind` | `0` = pedestal, `1` = pulser; no other value is legal |
| 4 | 4 | uint32 | `acq_seq` | acquisition sequence number within the lane |
| 8 | 4 | uint32 | `pulser_level` | commanded pulser DAC level; `0` on pedestal frames |
| 12 | 8 | int64 | `timestamp_ns` | crate timestamp in nanoseconds |
| 20 | 2 | uint16 | `sample_count` | inclusive range `64 .. 512` |
| 22 | 2 | int16 | `polarity` | `+1` or `-1`; no other value is legal |
| 24 | 4 | uint32 | `crc32` | CRC-32 of the sample payload bytes |

The frame payload is `sample_count` signed 16-bit samples, i.e. exactly
`2 * sample_count` bytes, immediately after the frame header.

## Sample coding and rails

Samples are two's-complement digitizer codes centred on zero. For `adc_bits = b` the
digitizer rails are

```
rail_low  = -2^(b-1)
rail_high =  2^(b-1) - 1
```

so a 12-bit crate spans `-2048 .. 2047` and a 14-bit crate spans `-8192 .. 8191`.

A sample outside `[rail_low, rail_high]` is a container violation and fails decoding.
A sample exactly equal to either rail is valid data that marks the frame as saturated
(`waveform.md`). Both rails count: a negative-polarity pulse saturates at
`rail_low`.

## CRC

`crc32` is the standard CRC-32 (as produced by `zlib.crc32`, masked to 32 bits)
computed over the **sample payload bytes only**. The frame header itself, the file
header, and any other frame are excluded from the payload integrity field. A mismatch fails decoding
and is never silently repaired or skipped.

## Decoder validation

Validation is performed in file order, and the first violation encountered aborts the
whole run. Decoding is total: a shard either yields exactly `frame_count` fully
validated frames and ends exactly at end of file, or it raises.

| Condition | Message must contain |
|---|---|
| File shorter than 24 bytes, or `magic != PMW2` | `unrecognized PMW2 shard` |
| `version != 2` | `unsupported PMW2 version` |
| `header_bytes != 24` | `unexpected file header size` |
| `adc_bits` not in `{12, 14}` | `unsupported adc_bits` |
| `reserved != 0` | `reserved file header field must be zero` |
| Fewer bytes remaining than a full frame header or payload | `truncated PMW2 frame` |
| `sample_count` outside `64 .. 512` | `sample_count out of range` |
| `kind` not in `{0, 1}` | `unknown frame kind` |
| `polarity` not in `{+1, -1}` | `invalid polarity` |
| Any sample outside the rails for `adc_bits` | `sample out of range for adc_bits` |
| Payload CRC does not match `crc32` | `sample payload CRC mismatch` |
| Bytes remain after the last declared frame | `trailing bytes after final frame` |

The trailing-bytes rule cuts both ways: a shard whose `frame_count` understates the
frames actually present fails exactly as a truncated shard does. Decoding must consume
the file exactly.

A shard file listed by a profile that does not exist or cannot be read fails the run
with a message containing `missing shard`.

Each decoded shard also carries its own byte length and the SHA-256 of its complete
file bytes, which the merge and the published artifacts rely on.

## Shard-set consistency

All shards named by one profile belong to one acquisition run and one crate
configuration.

| Condition | Message must contain |
|---|---|
| Two shards disagree on `run_id` | `mixed run_id across profile shards` |
| Two shards disagree on `adc_bits` | `mixed adc_bits across profile shards` |
| Profile names no shards | `profile has no acquisition shards` |
| Profile section absent from `runbook/campaign.toml` | `unknown profile` |

The run's `run_id` and `adc_bits` are the common values agreed by every shard, and
both are published.

## Merge

### Identity

An acquisition identity is the triple `(run_id, lane_id, acq_seq)`. At most one frame
per identity survives the merge. Identity deliberately excludes the timestamp and the
payload: two crates recording the same acquisition agree on the lane and the sequence
number, but may well disagree on the bytes.

### Shard priority

Shards are ranked by the key `(shard_index, basename)` ascending, independently of the
order in which the profile lists them. When two shards carry the same identity, the
frame from the higher-priority (lower-ranking-key) shard is retained and the other is
dropped. Because `basename` breaks ties, the ranking is a total order and the merge is
invariant under permutation of the profile's `shards` list.

Within a single shard, frames appear at most once per identity; if a shard repeats an
identity, the earlier occurrence in file order wins.

### Counters

The merge reports:

| Counter | Definition |
|---|---|
| `frames_read` | every frame decoded from every shard, before any rejection |
| `frames_rejected_duplicate` | frames dropped because their identity was already held |
| `frames_conflicting` | subset of the dropped duplicates whose payload differs from the retained frame |

Two frames "differ" when any header field other than the identity triple differs, or
when their sample payloads differ. A conflicting duplicate increments both counters;
an exact duplicate increments only `frames_rejected_duplicate`. A conflict is recorded,
not raised: the retained frame is still the one chosen by shard priority.

### Process order

After deduplication, surviving frames are sorted by

```
(timestamp_ns, kind, lane_id, acq_seq)
```

ascending. `kind` sorts before `lane_id` deliberately: when a pedestal frame and a
pulser frame carry the same timestamp, the pedestal (`kind = 0`) is processed first, so
the pulser sees the pedestal population that the crate had already recorded. This
four-key sort is a total order over surviving frames and is the documented process order
referenced by the rest of the contract.

The merged list is walked exactly once in this order. Frames are never regrouped by
lane before reduction, and a lane's frames are never processed as a contiguous block,
because either destroys the interleaving the pedestal model depends on.
