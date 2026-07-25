Hallwarden ML ops run a feature-pipeline training and inference eval lab under
/app for latch-contention energy. The model workflow expands quadratic features,
fits learning-cohort OLS weights, scores reserved-cohort inference with MAPE/R2
metrics, then emits a promotion plaque. The pass is a vault→forecast→emit
split: vault writes a durable design matrix, design vault, and latch pin under
/app/state; forecast reads that on-disk vault (never a fresh re-parse of labeled
traces) to fit train-cohort OLS weights, seal a beta–latch binding, score the
reserved cohort, seal emit trust, append a pass-chain line, and emit the plaque
gated by dual metric ceilings. Emit reloads staged state and re-checks emit
trust plus the beta–latch seal before rewriting the plaque. Outputs must stay
byte-stable under the same traces: offline verifiers recompute vault, latch_pin,
seal, fit, forecast, emit_trust, plaque, and pass-chain digests from /app/docs
with cohort and trunc rules.

Authoritative contracts live under /app/docs:

- /app/docs/ml-poly-ols-workflow.md
- /app/docs/specimen-vector-schema.md
- /app/docs/trunc-decimals-contract.md
- /app/docs/learning-reserved-cohort.md
- /app/docs/design-vault-contract.md
- /app/docs/latch-pin-contract.md
- /app/docs/beta-latch-seal-contract.md
- /app/docs/emit-trust-contract.md
- /app/docs/ols-beta-fit-contract.md
- /app/docs/fit-commit-contract.md
- /app/docs/mape-r2-metric-contract.md
- /app/docs/promotion-plaque-contract.md
- /app/docs/run-log-contract.md
- /app/docs/pass-chain-contract.md
- /app/docs/redrive-witness-rules.md
- /app/docs/hwml-cli.md
- /app/docs/specimen-catalog.md
- /app/docs/sidecut-offpath.md
- /app/docs/decoy-ignore-rules.md

Plaque field shapes also appear in /app/schemas/promotion_plaque.schema.json.
Latch pin field shapes appear in /app/schemas/latch_pin.schema.json.
Emit trust field shapes appear in /app/schemas/emit_trust.schema.json.
Beta–latch seal shapes appear in /app/schemas/beta_latch_seal.schema.json.

After one full training/inference pass write:

- /app/state/design_matrix.json
- /app/state/design_vault.json
- /app/state/latch_pin.json
- /app/state/beta_hat.json
- /app/state/fit_commit.json
- /app/state/beta_latch_seal.json
- /app/state/forecast_tape.json
- /app/state/emit_trust.json
- /app/state/run_log.jsonl
- /app/state/pass_chain.jsonl
- /app/plaque/promotion_plaque.json

Call /app/binx/hwml via /app/scripts/run-eval.sh (vault, forecast, or emit modes
allowed). Keep /app/sidecut and /app/decoy off the hot inference path.

Implement the vault→forecast→emit split so operators can validate
hash-pinned plaques under deterministic, byte-stable redrive.
