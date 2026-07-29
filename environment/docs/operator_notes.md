# Operator notes

Block-mirror maintenance after an inplace transfer drop. Destination length and mtime can look finished while sparse hole clusters and content-generation catchup still leave the independent probe elevated. The bundled liveness probe only checks catalog state flags; use the mirror replay driver from the task instruction for artifact validation.

## Replay workflow

From `/app`:

```bash
bash /app/environment/scripts/repro_mirror.sh
```

Environment variables:

- `OUTPUT_DIR` — artifact directory (required for verifier replay; default `/app/output` for agent runs)
- `MIRROR_ROOT` — workspace root (required for verifier replay; default `/app/environment`)
- `CYCLE_COUNT` — maintenance windows to replay (default `2`)
- `CYCLE` — single-cycle export when appending
- `APPEND_EXPORT=1` — retain prior artifacts on idempotent reruns

Scored verification rebuilds submitted sources from `MIRROR_ROOT`, checks `test -d /app/environment` before copy, and reruns `mirctl run` through `/tests/run_verifier_cycle.sh`. Verifier-only scripts are `/tests/rebuild_task_binaries.sh`, `/tests/verify_infra.sh`, and `/tests/run_verifier_cycle.sh`. Fresh binaries are built into `/tmp/verifier-bin`; scored replay runs as `VERIFIER_RUN_USER` (default `mirrun`).

Per-cycle fixture pairs are `catalog_view_a.json` / `probe_view_a.json` and `catalog_view_b.json` / `probe_view_b.json` under `fixtures/`. Catalog fixtures expose `finished`, `tally`, `epoch`, `state_flags`, `logical_path`, and `present_gen`. Probe fixtures expose `tally`, `epoch`, `hole_debt`, `holes_cleared`, `content_caught`, `present_mark`, `hole_clear_mark`, `content_mark`, `leg_a_io_done`, `leg_b_io_done`, `delayed_offset`, `delayed_span`, `leg_a_sum`, and `leg_b_sum`. Fixture booleans use JSON `true` / `false` polarity.

Pipeline binaries: `/app/bin/mirctl` (per-cycle export) and `/app/bin/viewctl` (catalog inspection). Rebuild both after editing sources under `/app/environment`.

The health probe is `bash /app/environment/signal/probe.sh` with `CYCLE` set per cycle.

## Replay artifacts

Exports land under `OUTPUT_DIR` (default `/app/output`):

- `push_trace.json` — `segments[]` with `leg_id`, `hold_ms`, `byte_offset`, `epoch`
- `rolling_digest.json` — latest-cycle `views[]` with `source`, `tally`, `epoch`, `tally_hex`
- `progress_trace.jsonl` — stage lines with `epoch`, `op`, `path`
- `convergence_report.json` — `cycles[]` with `cycle`, `synced_bytes`, `verified_bytes`

## Digest authority

Catalog tallies follow the active catalog fixture; probe tallies follow the active probe fixture. `rolling_digest.json` rows use the literal `source` strings `side-a` (catalog authority) and `side-b` (probe authority). Lane routing is in `config/epoch_lane.toml` via `catalog_lane` and `probe_lane`. Each `tally_hex` is lowercase sha256 over twelve little-endian bytes: uint64 `tally` then uint32 `epoch`.

Settlement overview for fixture field meanings is in `settlement_overview.md`. Export schemas, dual-axis gates, digest authority split, and leg-b advancement rules are in `export_contract.md`.

## Configuration tables

- `config/push.toml` — byte-span accounting and hold timing (`hold_us`)
- `config/epoch_lane.toml` — catalog and probe lane routing
- `config/payloads.toml` — logical path for progress traces
- `config/volumes.toml` — volume layout metadata

## Workspace layout

- `cmd/mirctl` and `cmd/viewctl` — maintenance CLIs
- `engine/` — cycle orchestration, segment merge, stage pipe, trace assembly, byte settlement
- `stride/` — segment row advancement
- `gate/` — stage pipe transitions
- `phase/` — digest view export
- `store/` — shared types, fixture blending, lane packing, ledger carry, sealed generation
- `fixtures/` — per-cycle catalog and probe views
- `data/seed_payload.bin` — delayed window byte sums for reconciliation checks
