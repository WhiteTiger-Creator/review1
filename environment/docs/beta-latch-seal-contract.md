# Beta–latch seal

Scheme `hwml.seal/v1` at `/app/state/beta_latch_seal.json`.

After beta_hat and fit_commit are on disk (and reloaded), forecast must seal
the binding between the learning fit and the staged latch pin:

- `beta_digest` — SHA-256 of `/app/state/beta_hat.json`
- `pin_digest` — SHA-256 of `/app/state/latch_pin.json`
- `vault_digest` — SHA-256 of `/app/state/design_vault.json`
- `pin_seq` — echoed from the on-disk latch pin
- `policy_epoch` — echoed from the workbook (must also match vault `policy_epoch`)
- `identity` — workbook identity

Forecast must reload the seal and refuse to continue when any bound digest
drifts from a fresh digest of the corresponding file, or when `pin_seq` /
`policy_epoch` disagree with the loaded latch pin / workbook.

Emit must reload `beta_latch_seal.json` and re-verify the same bindings before
rewriting the plaque. Mutating `beta_hat.json` without rewriting a matching
seal must abort emit.
