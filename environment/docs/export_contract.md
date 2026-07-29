# Block-mirror export contract

Maintenance replay exports land under `/app/output` after `bash /app/environment/scripts/repro_mirror.sh` or `/app/bin/mirctl run`.

| File | Role |
|------|------|
| `push_trace.json` | Segment rows accumulated across replay cycles |
| `rolling_digest.json` | Latest-cycle paired digest views |
| `progress_trace.jsonl` | Ordered stage lines per cycle |
| `convergence_report.json` | Synced vs verified byte counts per cycle |

## push_trace.json

JSON object with a `segments` array. Each element includes `segments[].leg_id`, `segments[].hold_ms`, `segments[].byte_offset`, and `segments[].epoch`.

Leg-a rows anchor at byte offset zero. Leg-b rows use the active probe fixture `delayed_offset` for every cycle, including append resume.

### Leg-b hold and epoch gate

Hold floor milliseconds equal `hold_us` from `/app/environment/config/push.toml` divided by 1000 (integer).

Leg-b baseline epoch is one less than the probe fixture epoch after lane routing from `/app/environment/config/epoch_lane.toml` (`catalog_lane` and `probe_lane`). When the two lanes differ, baseline uses the probe-routed epoch minus one, not the catalog epoch minus one.

Leg-b `hold_ms` must stay strictly below the hold floor while any of these remain open on the active probe fixture: destination IO incomplete (`leg_b_io_done` false), hole clearance incomplete (`holes_cleared` false), or content catchup incomplete (`content_caught` false). Closing only the hole axis or only the content axis is not enough; both axes must close together with destination IO before leg-b may advance.

When destination IO is complete and both settlement axes are closed on the probe fixture (`leg_b_io_done`, `holes_cleared`, and `content_caught` all true, with `hole_debt` zero), leg-b `hold_ms` must reach at least the hold floor and leg-b `epoch` must equal baseline plus one.

While destination IO remains incomplete, leg-b `epoch` must not exceed leg-a `epoch` for the same cycle.

Append resume rebuilds leg-b epoch floors from the active fixture pair, lane table, and whether the prior cycle recorded a `latch` line in `progress_trace.jsonl`, not from partial `verified_bytes` values in prior convergence rows. Leg-b epoch after append must stay at or above the probe fixture epoch - 1 after lane routing.

## rolling_digest.json

JSON object with a `views` array containing exactly two rows for the latest completed cycle. `views[].source` is the literal string `side-a` (catalog authority) or `side-b` (probe authority).

`views[].tally` follows the active catalog fixture for `side-a` and the active probe fixture for `side-b`. `views[].epoch` follows lane routing from `epoch_lane.toml`: catalog fixture epoch on `side-a`, probe fixture epoch on `side-b` when lanes differ.

Each `views[].tally_hex` is lowercase sha256 over twelve little-endian bytes: uint64 `tally` then uint32 `epoch`.

### Split authority during hole debt

When the catalog fixture reports `finished` true while probe `hole_debt` remains positive or content catchup is incomplete, digest authorities must stay split: `side-a` keeps the catalog fixture epoch and `side-b` keeps the probe fixture epoch. Finished catalog presentation must not collapse `side-a` onto the probe epoch, and must not copy probe epoch onto both views, while maintenance rank has not sealed a cycle whose `verified_bytes` caught up to `synced_bytes`.

Lane packing for snapshot blending must load `epoch_lane.toml` at runtime with distinct catalog and probe lanes rather than collapsing them.

## progress_trace.jsonl

One JSON object per line with `epoch`, `op`, and `path`. `path` matches the logical path from `/app/environment/config/payloads.toml`.

Per cycle, stage ops append in order `chunk`, then `roll`, then `latch`, after any prior cycle rows. `chunk` corresponds to presentation staging, `roll` to hole clearance, `latch` to content catchup.

## Phased settlement waves

Each replay cycle applies three settlement waves that must align with `progress_trace.jsonl` ops:

| Wave | Trace op | Effect |
|------|----------|--------|
| chunk | `chunk` | Stages presentation bytes on the stage pipe |
| roll | `roll` | Records hole-axis clearance on the stage pipe |
| latch | `latch` | Records content catchup on the stage pipe |

The stage pipe may close only after all three waves complete and both settlement axes agree on the active probe fixture. Wave application builds a working pipe; coordinator bind, verified accounting, and digest export consult the finalized pipe after all waves apply. `synced_bytes` may reflect staged presentation after the chunk wave. `verified_bytes` may equal `synced_bytes` only after chunk, roll, and latch waves all complete, the finalized stage pipe is closed with both settlement axes agreeing on the active probe fixture, and the probe fixture reports hole debt cleared with both `holes_cleared` and `content_caught` true and `hole_debt` at zero. Partial wave progression — chunk alone, or chunk plus roll without latch — must not credit verified bytes even when synced presentation is positive.

Leg-b advancement and digest sealing consult finalized coordinator state together with probe fixture axes — not presentation flags alone.

## convergence_report.json

JSON object with a `cycles` array. Each element includes `cycles[].cycle`, `cycles[].synced_bytes`, and `cycles[].verified_bytes`.

`synced_bytes` reflects staged presentation bytes once the stage pipe accepts presentation. `verified_bytes` may equal `synced_bytes` only after the stage pipe is closed and the probe fixture reports hole debt cleared, holes cleared, and content caught with `hole_debt` zero.

Maintenance rank and sealed generation count only cycles where `verified_bytes` equals `synced_bytes` and both are positive. Cycle one with finished catalog presentation but open hole or content axes must keep `verified_bytes` below `synced_bytes` and rank seal at zero.

## Idempotent append

Re-running `/app/bin/mirctl run /app/output` with `APPEND_EXPORT=1` for an already-exported settled cycle must not duplicate `push_trace.json` segment rows, `convergence_report.json` cycle entries, or `progress_trace.jsonl` lines, and must not replace `rolling_digest.json` when the cycle was already sealed.

## Delayed window reconciliation

Probe fixtures expose `delayed_offset`, `delayed_span`, `leg_a_sum`, and `leg_b_sum` against `/app/environment/data/seed_payload.bin`. On cycle one with open settlement axes, `leg_b_sum` may disagree with `leg_a_sum` even when catalog `finished` is true. After both axes close on cycle two, leg sums converge and the final cycle row must show `verified_bytes` equal to `synced_bytes`.

## Incremental append equivalence

Running cycle one and appending cycle two with the append flag from a clean output directory must produce the same `push_trace.json`, `progress_trace.jsonl`, `convergence_report.json`, and `rolling_digest.json` artifacts as a single two-cycle replay from a clean output directory.
