# CLI

`/app/binx/hwml vault|forecast|emit|eval`

- `vault` — load specimens → design matrix, design vault, latch pin under `/app/state`
- `forecast` — reload staged vault + latch_pin → beta, fit commit, beta–latch seal,
  forecast tape, emit trust, run log, pass-chain append, plaque
- `emit` — reload existing state; verify emit trust + beta–latch seal; rewrite plaque;
  append one emit-witness line (no re-fit, no trace parse, no pass-chain append —
  see `/app/docs/redrive-witness-rules.md`)
- `eval` — vault then forecast (default for `/app/scripts/run-eval.sh`)

`HWML_WORKBOOK` / `HWML_TRACES` override fixture paths.
