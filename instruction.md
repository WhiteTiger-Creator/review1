# Jacobian sensitivity numeric parity

A minimized implicit-step sensitivity lab under `/app/environment` drives `/app/bin/q7` through checkpointed `start` / `seal` / `resume` segments that emit per-tile linearization rows for stiff coupled models. Rebuilt runs must satisfy `/app/environment/docs/n4_rules.md` on element deltas against the extended-precision reference, fine finite-difference probe slopes at each `dt_fine` entry, large-step spectral stability at `dt_large`, sealed-segment checkpoint continuity, second-generation lineage replay, and reproducibility digests. Tolerances and formulas live in that contract (`ELEM_TOL = 1e-10`, `FINE_BAND = 1e-8`, `STAB_CAP = 2.0`, `LARGE_DT = 0.28`, `BIND_K = 1e-6`, `BIND_SCALE = 1e-10`).

Bring the numerical pipeline into compliance with that contract so rebuilt `/app/bin/q7` regenerates authoritative traces. Fix C source under `/app/environment` as needed for contract compliance; wrapper-only or CLI-only changes are not sufficient. Rebuild with `make -C /app/environment all`, then run the documented segmented workflow:

```bash
/app/bin/q7 --mode start --state-dir /app/output/q7_state \
  --model /app/environment/fixtures/stiff_coupled.json \
  --trace-out /app/output/sensitivity_trace.json --profile nominal
/app/bin/q7 --mode seal --state-dir /app/output/q7_state \
  --trace-out /app/output/sensitivity_trace.json
/app/bin/q7 --mode resume --state-dir /app/output/q7_state \
  --model /app/environment/fixtures/stiff_coupled.json \
  --trace-out /app/output/sensitivity_trace.json --profile scaled
```

Successful compliance regenerates `/app/output/sensitivity_trace.json` whose rows identify each tile by id, carry reported and reference numeric values with the active profile name, include emit-lane tags from the cast path, and finish with a sixteen-character reproducibility digest. The public trace keys tile_id, reported, reference, profile, emit_lane, and repro_digest are defined in n4_rules.md. Static JSON writes, wrapper-only changes, and placeholder digests are insufficient; the verifier deletes the output and reruns the segmented driver on every accepted fixture.
