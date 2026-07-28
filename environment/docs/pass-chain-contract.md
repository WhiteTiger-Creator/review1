# Pass chain

Path: `/app/state/pass_chain.jsonl`

After each successful plaque write (forecast or eval), append one UTF-8 JSON
line. Stage byte artifacts under `/app/state` (except this chain file and
`run_log.jsonl`) and the plaque must stay byte-stable across redrive while the
chain grows.

Each line includes:

- `pass_index` — 1-based line count after append
- `prior_digest` — previous line's `chain_digest`, or empty string on the first pass
- `stage_fingerprint` — SHA-256 hex of the pipe-joined digests
  `vault|pin|beta|commit|seal|forecast|trust` (each SHA-256 of the matching
  on-disk file under `/app/state`)
- `vault_digest` — SHA-256 of `design_vault.json`
- `seal_digest` — SHA-256 of `beta_latch_seal.json`
- `pin_seq` — integer from the on-disk latch pin
- `chain_digest` — SHA-256 hex of
  `prior_digest|stage_fingerprint|vault_digest|seal_digest|pin_seq|pass_index`
  (pipe-separated, no spaces; `pin_seq` and `pass_index` as decimal text)

Vault-only mode must not append. Emit-only plaque rewrite must not append here —
successful emits append to the separate emit witness ledger instead
(`/app/docs/redrive-witness-rules.md`).
