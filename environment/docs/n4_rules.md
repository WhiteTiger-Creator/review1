# Numeric contract (n4)

## Checkpointed segments

Sensitivity traces are produced through alternating checkpoint segments under a state directory. Build with `make -C /app/environment all`, then drive `/app/bin/q7` in three modes:

```
/app/bin/q7 --mode start --state-dir <STATE> --model <fixture> --trace-out /app/output/sensitivity_trace.json --profile nominal
/app/bin/q7 --mode seal --state-dir <STATE> --trace-out /app/output/sensitivity_trace.json
/app/bin/q7 --mode resume --state-dir <STATE> --model <fixture> --trace-out /app/output/sensitivity_trace.json --profile scaled [--dt SECONDS]
```

`start` initializes generation `0` with effective seed `0`. `seal` marks the active slot sealed, stores the trace `repro_digest`, derives `bind_seed`, computes a lineage seed, increments `generation`, and rotates the active slot. `resume` requires at least one sealed slot; it returns exit code `64` when no sealed slot exists.

Checkpoint files under `<STATE>`:

- `head.json` object with integer `generation`, integer `active_slot` (`0` or `1`), and integer `segment_id`
- `slot_0.json` and `slot_1.json` objects with integer `sealed` (`0` or `1`), string `digest` (16 lowercase hex), float `bind_seed`, float `lineage_seed`, and integer `slot_generation`

`bind_seed = int(first_8_hex(repro_digest), 16) * BIND_SCALE` with `BIND_SCALE = 1e-10`.

After `seal`, the sealed slot's stored `bind_seed` must equal the digest decode within absolute tolerance `1e-20`. The sealed slot's `slot_generation` must equal the post-seal head generation. For the first sealed generation, `lineage_seed = bind_seed`, checked as `abs(lineage_seed - bind_seed) <= 1e-20`. For later sealed generations, `expected_lineage = bind_seed + 0.25 * previous_newest_lineage_seed`, checked as `abs(lineage_seed - expected_lineage) <= 1e-20`; the previous value comes from the newest sealed slot before the current seal.

`resume` uses the newest sealed slot by `slot_generation`, not merely the active slot. The resumed effective seed is that slot's `lineage_seed` when positive, otherwise its `bind_seed`, otherwise the decoded digest. On torn or truncated slot files, recovery must still choose the newest intact sealed slot before deriving the effective seed.

When `generation > 0`, effective shift for both reference and reported paths is `shift_eff = shift + BIND_K * effective_seed` with `BIND_K = 1e-6`. Generation `0` uses `shift_eff = shift`.

## Element band

For tile row `k` with quad reference `ref_k` and driver-reported `rep_k` at active `shift_eff`:

`elem_delta_k = |rep_k - ref_k| / max(|ref_k|, 1e-14)`

Policy requires `elem_delta_k <= ELEM_TOL` with `ELEM_TOL = 1e-10` on accepted fixtures at the active `dt_step` for every segment mode.

## Reported row source

For `dt < LARGE_DT`, each row `reported` value is the assembled tile pipeline output from the emitted lambda, libm chain binding, and Jacobian grouping under the active effective seed and generation. For `dt >= LARGE_DT`, `reported` is the tile state after the step-advance module updates that pipeline value. In both cases `reported` must match the quad reference at the same `shift_eff` and `dt` within `ELEM_TOL` under a compliant build.

## Emit lane tag

Each row includes `emit_lane`, a four-character lowercase hex tag derived from tile depth and emitted lambda:

`emit_lane = lower_hex4((depth * 7919 + int(|lambda_emit| * 1e4)) XOR int(effective_seed * 1e8))`

The tag must be produced by the emission path and must match this formula for resumed segments as well as start segments.

## Large-step band

`LARGE_DT = 0.28`

Accepted fixtures must satisfy `rho(dt_large) <= STAB_CAP` with `STAB_CAP = 2.0` where `rho` is the `v9_stab` spectral measure at the fixture `dt_large` value and active `shift_eff`.

## Fine-probe band

Fine probe class uses `h = dt * 0.25` forward differences. On each `dt` in `dt_fine`, compare the driver `reported` slope `(rep(dt + h) - rep(dt)) / h` to the reference probe `(v9_elem(dt + h) - v9_elem(dt)) / h` within `FINE_BAND = 1e-8` for every tile after a resumed segment.

## Reference formula

For each tile:

`lambda_t = diag[t] + shift_eff - abs(off[t-1]) - abs(off[t])`

Missing off-diagonal terms at the boundaries are omitted. With `p(nominal)=1` and `p(scaled)=1+1e-7`:

`v9_elem(t) = (1 / (1 - dt * lambda_t)) * (1 + log1p(dt * |lambda_t| * 0.1) * p(profile))`

If `|1 - dt * lambda_t| < 1e-18`, the reference element is zero.

`v9_stab(dt) = max_t |1 / (1 - dt * lambda_t)|`, with `1e6` returned for near-zero denominators.

## Trace row schema

`/app/output/sensitivity_trace.json` is a JSON object:

- `rows`: array of objects sorted by driver emission order
- `repro_digest`: sixteen-character lowercase hex digest over the canonical rows body

Each row object contains:

- `tile_id`: string integer tile id
- `reported`: float
- `reference`: float
- `profile`: string `nominal` or `scaled`
- `emit_lane`: four-character lowercase hex

The digest body is `{"rows":[...]}` with row keys in exactly this order: `tile_id`, `reported`, `reference`, `profile`, `emit_lane`. Floating values are formatted with `%.17g`.

The placeholder digest `deadbeefdeadbeef` is reserved for tamper checks and must never appear as a valid regenerated `repro_digest`.

## Accepted fixtures

| Fixture | Role |
|---|---|
| `/app/environment/fixtures/stiff_coupled.json` | primary stiff coupled model |
| `/app/environment/fixtures/shifted_stiff.json` | shift metamorphic baseline |
| `/app/environment/fixtures/asymmetric_tiles.json` | asymmetric tile count / stiffness |

Each fixture JSON object includes integer `n`, float `shift`, arrays `diag` and `off`, float `dt_step`, array `dt_fine`, and float `dt_large` (must be `>= LARGE_DT`).

## Coefficient-set labels

| CLI `--profile` | Scale |
|---|---|
| `nominal` | 1 |
| `scaled` | 1 + 1e-7 |

Both coefficient sets must satisfy the element band and large-step band on accepted fixtures under a compliant build after `resume`.

## Metamorphic shift rule

For `shifted_stiff.json` resumed after seal, trace row ordering by `tile_id` must remain identical to `stiff_coupled.json`. Each row's `reference` and `reported` fields must match `v9_elem` for the shifted fixture within `ELEM_TOL` at the resumed `shift_eff`. When the fixture `shift` offset is nonzero, at least one tile's `v9_elem` reference must differ from the unshifted fixture by more than `META_TOL = 1.0e-10` relative element distance.

## Delayed lineage compliance

A compliant `start` segment on `nominal` with effective seed `0` may already meet the element band. Under the same fixtures, sealed then resumed segments on `scaled` with derived effective seed greater than zero must also meet the element band, fine-probe, large-step, and digest rules at the resumed `shift_eff`. Re-sealing a resumed trace creates a second-generation lineage seed, so a later resume must not silently fall back to the older sealed slot.
