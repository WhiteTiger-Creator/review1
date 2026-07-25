# Fit commit

Path: /app/state/fit_commit.json

Scheme hwml.commit/v1. Written after beta_hat is on disk. Pins the vault that was
used for the fit.

Required fields:

- scheme, identity
- vault_digest — sha256 hex of /app/state/design_vault.json bytes
- beta_digest — sha256 hex of /app/state/beta_hat.json bytes
- learning_ids — learning cohort ids in ascending string order (must match vault
  learning rows)

A commit whose vault_digest does not match the on-disk vault is invalid even if
beta values look plausible.
---

Scheme id: hwml.commit/v1
