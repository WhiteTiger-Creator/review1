# Emit trust contract

Scheme `hwml.trust/v1` at `/app/state/emit_trust.json`.

After the forecast tape and beta–latch seal are on disk and before the promotion
plaque is written, seal an emit-trust record that binds the staged artifacts
used for promotion:

- `vault_digest` — SHA-256 of `/app/state/design_vault.json`
- `pin_digest` — SHA-256 of `/app/state/latch_pin.json`
- `beta_digest` — SHA-256 of `/app/state/beta_hat.json`
- `commit_digest` — SHA-256 of `/app/state/fit_commit.json`
- `seal_digest` — SHA-256 of `/app/state/beta_latch_seal.json`
- `forecast_digest` — SHA-256 of `/app/state/forecast_tape.json`
- `mape`, `r2`, `metrics_pass` — echoed from the on-disk forecast tape
- `identity` — workbook identity

Plaque emission must reload `emit_trust.json` from disk and refuse to proceed
when any bound digest no longer matches a fresh digest of the corresponding
file, or when `metrics_pass` / mape / r2 disagree with the on-disk forecast tape.

The `hwml emit` mode reloads existing state (no re-fit) and re-checks emit trust
plus the beta–latch seal before rewriting the plaque. Stale trust after a
mid-flight mutation of beta, fit commit, seal, or forecast tape must exit
non-zero.

Forecast that re-parses labeled traces instead of consuming the staged vault is
still non-compliant even when emit trust digests look locally consistent.
