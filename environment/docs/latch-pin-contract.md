# Latch pin contract

Scheme `hwml.pin/v1` at `/app/state/latch_pin.json`.

After the design vault is written, compute:

- `vault_digest`: SHA-256 hex of the on-disk `/app/state/design_vault.json` bytes.
- `row_count`: number of rows in the vault.
- `identity`: workbook identity echoed from the vault.
- `policy_epoch`: workbook `policy_epoch` echoed into the pin.
- `pin_seq`: if a prior latch_pin exists with the same `vault_digest`, reuse that
  pin_seq; otherwise set `pin_seq = prior_pin_seq + 1` (or `1` when no prior
  latch_pin file exists). Only the immediately prior on-disk latch_pin
  participates in this comparison — earlier digests are not remembered, so a
  vault that returns to a previously seen byte state after an intervening
  change still takes `prior_pin_seq + 1`.

Forecast must reload both the vault and the latch_pin from disk and verify
`vault_digest` equals a fresh digest of the loaded vault file before fit/score,
and that vault/`policy_epoch` matches the workbook epoch.
Plaque records echo `pin_digest` (sha256 of the latch_pin file bytes) and
`pin_seq`.
