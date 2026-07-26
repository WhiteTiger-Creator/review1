# Residual scope report contract

Authoritative long spans live under `/app/environment/fixtures/annex/`. Combined whitespace token floor is 52000 across all annex files. Partial excerpts under `/app/environment/fixtures/excerpts/` omit rows and must not override annex bytes.

## Lab drivers

Feature and window tables are produced by `bash /app/environment/scripts/stage_tables.sh` (writes `/app/output/m1_tables.rds`). Staged-table column names and types are defined in `/app/environment/docs/col_layout.md`.
Witness fit for fold scoring is driven by `bash /app/environment/scripts/drive_suite.sh` (writes `/app/output/m2_witness.rds`).

## Bundle annex filenames

Annex file `bundle_w3.txt` means the long deposition span for bundle w3. `bundle_w4.txt` and `bundle_k5.txt` mean the matching spans for w4 and k5.

## Inspect helpers

Validation helpers used by the residual-scope path.

```bash
bash /app/environment/scripts/inspect_cols.sh
bash /app/environment/scripts/inspect_join.sh
bash /app/environment/scripts/inspect_chain.sh
bash /app/environment/scripts/inspect_mono.sh
```

Script `inspect_cols.sh` prints staged window-table column names. Script `inspect_join.sh` reports whether judgment `doc_id` values are present in staged window tables. Script `inspect_chain.sh` rebuilds `chain_hex` for a bundle and tag pair. Script `inspect_mono.sh` reports whether `score` values are monotonic under the active profile `fold_order`.

## Graded residual-scope checker

Script `run_scope_chk.sh` means it runs the graded residual scope checker and writes the terminal JSON report when feature build and witness fit have produced fresh tables.

```bash
bash /app/environment/scripts/run_scope_chk.sh --suite all --tags strict_mono,relaxed_fast --bundle-out /app/output/residual_scope.json
```

Success requires exit code 0 for bundles `w3`, `w4`, and `k5` under both numeric tags `strict_mono` and `relaxed_fast`.

The judgment TSV files provided to the lab drivers may be incomplete. If an interim snapshot for a bundle exists (e.g. `interim_snaps/q2_part.json`), its `residual_rows` list contains historical adjustment bands. Any `doc_ix` matching a `row_ix` from this file must have its `relevance` multiplier adjusted by `1.0 + band` using the logic defined in the historical policy engine (`rk4/legacy_e.R` or equivalent). This merge must happen during the `m1_tables.rds` generation.

## Multi-pass Cache Coherence

The witness fit process runs multiple times (epochs) driven by `drive_suite.sh`.
`chain_hex` is lowercase hex encoding of the concatenated canonical replay bytes from `op_m3` in `/app/environment/rp3/loop_c.R` (no SHA256 digest). 
Replay layout uses magic `RLCR`, a row count word, then per row a bundle byte (w3 as 1, w4 as 2, k5 as 4), a tag byte (strict_mono as 0, relaxed_fast as 1), a fold byte (alpha as 1, beta as 2, gamma as 3), then float64 residual and float64 score.
**Critical**: If `op_m3` is called with `refresh_flag = FALSE` and the cache file exists, it must APPEND its canonical replay bytes to the existing cache file. It must NOT overwrite. If `refresh_flag = TRUE`, it must reset the cache. The reported `chain_hex` will be evaluated over the fully concatenated multi-epoch ledger.

## Monotonic Constraint Optimization

Top-level object members in `/app/output/residual_scope.json` contain `bundles` map with tag blocks. Each tag block contains `residual_rows`, `chain_hex`, and `mono_band`.

Within each tag block, `score` values must be strictly monotonically increasing (`diff(scores) >= 1e-9`) when rows follow fold order from the active profile TOML under `/app/environment/profiles/`. 
The `score` for a fold is initialized as `base_pred + fold_adjustment`, where `base_pred` is the mean relevance of the reconstructed judgments, and `fold_adjustment` is `0.04 * fold_index` (1-based index based on `fold_order`).
The residual is exactly `score - base_pred`.
Each `residual` must satisfy `abs(residual) <= residual_floor + band_eps`.
If the initial score violates the strict monotonicity constraint, the solver must iteratively add `1e-9` to the minimal number of folds required to restore monotonicity, provided that no residual exceeds the bound.

## Recovery after cache wipe

Cache wipe path shown below.

```bash
bash /app/environment/migrations/cln4.sh
```

That script may remove cached RDS tables under `/app/output/`. Recover by regenerating feature tables and witness fit through the lab drivers above, then rerunning the graded checker.
