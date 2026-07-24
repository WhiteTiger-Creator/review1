# YOD simulation protocol

Yard observations move through three numerical stages of the Yard Occupancy Dynamics study: bind the corpus into a staged graph state, solve a capacity-feasible occupancy trajectory, then publish sealed geometric path-integral atlas observables.

## Stages

1. ingest: raw yard geometry and consist -> /app/state/yard-staging.json plus /app/state/ingest-snapshot.json with stable staging_hash
2. optimize: staging graph -> capacity-feasible move list plus residual-graph LEAD closure -> /app/state/shunting-validated.json
3. export: sealed solved state -> /app/output/shunting-sequence.json plus /app/state/export-manifest.json and /app/state/export-ledger.json

## Data-flow rules

- optimize reads only /app/state/yard-staging.json and must not re-load topology or consist from the raw yard directory
- export reads only /app/state/shunting-validated.json and must not re-load raw yard files
- HFSY_YARD_DIR overrides the default /app/yard-alpha corpus root for ingest
