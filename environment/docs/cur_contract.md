# Curriculum learning training-loop contract

This document defines the public training-sampler contract for a local curriculum-learning model trainer. The harness schedules train and held-out evaluation cohorts across training epochs, updates competence from learning signals, and resumes after a training-checkpoint interrupt.

## Commands

Build:

```
/app/environment/scripts/build_cqrun.sh
```

Also reachable as `/app/scripts/build_cqrun.sh`.

Writable `HOME=/tmp` (and `GOCACHE` under `/tmp`) is assumed for the offline Go toolchain when the process home is not writable.

Run a full session (two epochs, forced interrupt after epoch 1 barrier, then resume):

```
/app/bin/cqrun run --packs /app/packs --out /app/output/cohort_trace.json --state /app/output/cohort_state
```

Policy knobs live in `/app/docs/pol_a.toml` (epochs, alpha, fence_lag, band_cuts, interrupt_after_epoch, weight_decimals).

Packs are JSON files under `/app/packs` named `seed_*.json`. Each pack has `id` (string), `items` (array). Each item has `item_id` (string), `prior` (float in [0,1]), `signal` (float in [0,1]).

## Trace schema

Root object: `rows` (array) and `summary` (object).

Row keys:
- `scenario_id` (string): pack id
- `epoch` (integer): 1-based epoch index
- `item_id` (string)
- `band` (integer): difficulty band 0..3
- `role` (string): `train` or `eval`
- `admit_hex` (string): lowercase hex, 16 chars
- `fence_hex` (string): lowercase hex, 16 chars
- `weight` (number): competence weight recorded on that row

Summary keys:
- `epochs` (integer): epochs executed (2 for the standard run)
- `rows_total` (integer): length of `rows`
- `cohort_digest` (string): lowercase hex, 16 chars
- `resume_digest` (string): lowercase hex, 16 chars
- `fence_status` (string): `sealed` or `leaky`
- `wal_depth` (integer): field counts durable WAL entries after the final barrier

## Derivations

Shared offline helpers: `/app/environment/scripts/ref_kit.py`.

1. Band assignment: given weight `w` and `band_cuts` sorted ascending, `band` is the count of cuts strictly less than `w`.
2. Competence update on a train admission with current weight `w` and item `signal` `s` is computed as `w' = (1 - alpha) * w + alpha * s`, where `alpha` means the EMA mixing rate from pol_a.toml. Eval admissions do not change competence; they record the current weight.
3. Initial weight for an item is its pack `prior`. After an interrupt, weights must be rebuilt by replaying every durable WAL entry from those priors (not by trusting a snapshot blob alone).
4. Cohort split per pack per epoch, with `n` items and `train_n = n / 2` (integer division):
   - Let `F` be the set of `(scenario_id, item_id)` pairs that had a train admission in any epoch `K` where `E - fence_lag <= K <= E - 1` (empty when that window is empty).
   - Eval cohort: items not in `F`, sorted by weight ascending then `item_id` ascending, take the first `n - train_n` items. If fewer than `n - train_n` candidates exist, the run is invalid under this policy (packs are sized so this does not happen for fence_lag=1).
   - Train cohort: the remaining items, sorted by weight descending then `item_id` ascending, take `train_n` items (packs keep even length so this fills exactly).
5. Emission order: epochs ascending; within an epoch, packs by ascending `scenario_id`; within a pack, all train rows (by the train cohort sort) then all eval rows (by the eval cohort sort).
6. Eval fence bit: an eval row is illegal when its `(scenario_id, item_id)` is in `F` for that epoch. Train rows always use fence bit `0`. Correct cohort selection yields no illegal eval rows; a selection that ignores `F` can admit illegal eval rows.
7. `admit_hex` is the first 16 hex chars of sha256 over UTF-8 `scenario_id|item_id|epoch|role|band`.
8. `fence_hex` is the first 16 hex chars of sha256 over UTF-8 `admit_hex|` plus the decimal fence bit (`0` or `1`).
9. `cohort_digest` is the first 16 hex chars of sha256 over all row `admit_hex` values sorted lexicographically and joined with commas.
10. `resume_digest` is the first 16 hex chars of sha256 over pairs `scenario_id/item_id:weight` after the final replay, with weight formatted to `weight_decimals` places (`weight_decimals` means the printed precision from pol_a.toml), pairs sorted lexicographically by `scenario_id/item_id`, joined with commas.
11. `fence_status` is `sealed` when every row has fence bit `0`; otherwise `leaky`.
12. Standard run forces an interrupt after the epoch-1 barrier: durable state under `--state` is closed, logic resumes from that state, then epoch 2 runs. A second full `cqrun run` with the same packs must rewrite identical `cohort_trace.json` field values.

## Coherent vs incoherent

Coherent: `fence_status` is `sealed`, `resume_digest` matches derivation 10 after WAL replay, and `cohort_digest` matches derivation 9.

Incoherent: at least one of those fails. Local per-epoch train counts alone are not enough.
