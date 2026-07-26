# Trust digest canon

## Field vocabulary

Consumer trust decisions bind window-table fields from the anchors tree:

- `legacy` — generation retained before a cutover tip advances
- `tip` — generation marked current when the slot is not dual
- `dual` — whether the slot is currently advertising a dual-generation window
- `a`, `b` — generation bounds that define the live set while `dual` is true

Grace rows under the cache tree use `deadline`, `skew`, `held`, and `next` for retained polarity selection. Pairing rows under the corpus tree map publication ids to parent submission tokens.

## Digest composition

`matrix_digest` binds one authorized trust decision. It is the first 16 lowercase hex characters of SHA-256 over the UTF-8 string:

  scenario_id + "|" + outcome

No whitespace between fields. `outcome` is the allow or deny token the live desk emits for that scenario after its authorization path finishes. Local probe CLEAN does not contribute to this digest.
