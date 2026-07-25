# Poly-OLS loop

Hallwarden latch forecast is a staged machine-learning lab:

1. **Vault** loads the workbook and labeled specimen traces, expands the quadratic
   design matrix (with `policy_epoch` echoed from the workbook), writes
   `/app/state/design_matrix.json` and `/app/state/design_vault.json`, then seals
   `/app/state/latch_pin.json`. Vault mode must not write beta, seal, trust, plaque,
   or pass-chain lines.
2. **Forecast** reloads the on-disk vault and latch_pin (never re-parses traces),
   refuses when `policy_epoch` drifts from the workbook or when latch_pin
   `vault_digest` mismatches on-disk vault bytes, fits learning-cohort OLS beta,
   writes fit commit + beta–latch seal + forecast tape, seals emit trust (including
   `seal_digest`), writes the stage run log, appends a pass-chain line, then emits
   the promotion plaque.
3. **Emit** reloads existing state artifacts, verifies emit trust and the
   beta–latch seal against on-disk digests, and rewrites the plaque without
   re-fitting and without appending a pass-chain line.

Scheme family: `hwml.*/v1`. Fit and forecast stages reload vault/beta/seal
artifacts from disk after each write. Reference math in the offline verifier is
binding. Truncation follows `/app/docs/trunc-decimals-contract.md`.

Forecast must refuse to proceed when the latch_pin vault_digest does not match a
fresh digest of the on-disk design vault. Emit must refuse when emit_trust or
beta_latch_seal digests drift from staged bytes.

Memory-only shortcuts that skip vault, latch_pin, seal, or emit_trust persistence
are non-compliant.

Workflow id: hwml.loop/v1

Operators run an offline inference pass after training on the learning cohort.

Native ML surface: quadratic polyols, ridge_lambda bait, MAPE/R2 dual ceilings,
latch-contention energy, reserved-cohort inference tape, policy_epoch invalidation.
