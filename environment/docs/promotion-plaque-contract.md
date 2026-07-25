# Promotion plaque

Path: /app/plaque/promotion_plaque.json

Scheme hwml.plaque/v1 fields:

- identity, promoted, finished, mape, r2, mape_ceiling, r2_floor, policy_epoch
- design_digest, beta_digest, forecast_digest — sha256 of the corresponding
  /app/state/*.json files
- vault_digest — sha256 of /app/state/design_vault.json
- fit_commit_digest — sha256 of /app/state/fit_commit.json
- pin_digest — sha256 of /app/state/latch_pin.json
- seal_digest — sha256 of /app/state/beta_latch_seal.json
- trust_digest — sha256 of /app/state/emit_trust.json
- pin_seq — echoed from the latch pin
- policy_epoch — echoed from the workbook

promoted is true only when the on-disk emit trust reports metrics_pass true
(MAPE and R2 dual gate with non-empty reserved rows). Digests bind on-disk bytes
after all state files including emit_trust and beta_latch_seal are written.

Scheme id: hwml.plaque/v1
