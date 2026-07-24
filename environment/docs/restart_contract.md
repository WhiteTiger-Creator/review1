# Restart contract

Public format and observation contract for the x7 continuum restart stack under
`/app/environment`.

## Entry

```bash
bash /app/environment/h1/run_x7.sh
/app/environment/tools/x7_gate --matrix-full --out /app/output/run-record.json --final /app/output/final.h5
```

Binary: `/app/environment/bin/x7_orch`.

## Matrix

| Scenarios | Profiles | Transitions |
|-----------|----------|-------------|
| `sa`, `sb`, `sc` | `px`, `qy` | `n2_to_n5`, `n5_to_n3`, `n3_to_n4`, `n4_same` |

Configs: `environment/cfg_store/cfg_<scenario>.json`.
Profiles: `environment/profiles/<profile>.prof` (`KAPPA`, `DT0`, `CFL`, `TOL`).

## Numerical model

Adaptive one-dimensional FTCS diffusion. Controller state persisted across
checkpoints:

- `last_dt` — last accepted timestep
- `n_reject` — rejected proposal count
- `n_accept` — accepted step count
- `accum` — EMA of accepted `max|du|` used when proposing the next step

Proposal uses growth factor `1.1` capped by the CFL limit. Acceptance compares
the communicator-wide maximum absolute update against `TOL` scaled by the
controller accumulator. Mass observations use a process-count-independent
accumulation over the global field in GID order with tolerance `1e-12`.

Fresh and continued trajectories for the same scenario and profile must match
on field digest, accepted `dt` sequence, mass sequence, and controller state.

## Checkpoint layouts

1. **Legacy (`layout=1`)** — root datasets `owned_rK`, `ghost_lo_rK`,
   `ghost_hi_rK`, `gids_rK`, root `/hist`, optional root controller attributes.
2. **Grouped (`layout=2`)** — `/gen_XXXX/` rank blocks with shared `/hist`
   (and `/ctrl` when present).
3. **Gen-local (`layout=3`)** — each generation owns `hist/`, `ctrl/`,
   `fingerprint`, `field_cksum`, and a commit marker.

Writer failpoints via `X7_FAILPOINT`:

- `after_rank_block:N`
- `after_history`
- `before_commit`
- `before_publish_rename`

## Recoverable generation

A generation is recoverable only when all of the following hold:

1. `committed = 1`
2. Every declared writer rank block exists
3. Owned and GID lengths agree
4. Owned GIDs cover `[0, n_global)` exactly once
5. History length and controller counters agree with the generation step
6. Controller state is complete
7. Fingerprint matches the requested profile and configuration
8. `field_cksum` matches owned values reconstructed in GID order
9. All required values are finite
10. The layout is supported

Continuation selects the newest recoverable generation. Incompatible profile or
configuration state must fail without publishing a new final artifact.

## Outputs

Graded artifacts:

- `/app/output/final.h5` — global `owned`, `/hist/{dt_seq,mass_seq}`, `/ctrl`
- `/app/output/run-record.json` — observation rows emitted by `x7_gate`

Field digest: SHA256 of little-endian IEEE754 float64 values in GID order.

## Publication and immutability

Final publication is atomic: no partial `final.h5` after a forced publish
failure. Successful continuation must leave supplied checkpoint bytes unchanged.
Repeating the same continuation is idempotent for owned state, accepted
timestep history, mass history (within `1e-12`), and controller state.
