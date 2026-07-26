# Redrive and emit witness rules

Successful forecast/eval passes are idempotent under unchanged traces: stage
artifact bytes stay fixed while `pass_chain.jsonl` grows. Operators treat each
pass-chain line as a witness of the prior seal/tape binding.

## Emit witness ledger

Path: `/app/state/emit_witness.jsonl`

Only a **successful `emit`-mode plaque rewrite** appends one UTF-8 JSON line to
this ledger. Vault, forecast, and eval modes never create or touch it. An emit
that aborts (stale emit trust, stale beta–latch seal, or missing staged
artifacts) must not create the file and must not append to an existing one.

Each line is appended after the plaque file is rewritten and includes:

- `witness_index` — 1-based line count after append
- `prior_digest` — previous line's `witness_digest`, or empty string on the
  first witness
- `plaque_digest` — SHA-256 hex of the rewritten
  `/app/plaque/promotion_plaque.json` bytes
- `trust_digest` — SHA-256 hex of `/app/state/emit_trust.json` bytes
- `seal_digest` — SHA-256 hex of `/app/state/beta_latch_seal.json` bytes
- `pin_seq` — integer from the on-disk latch pin
- `witness_digest` — SHA-256 hex of
  `prior_digest|plaque_digest|trust_digest|seal_digest|pin_seq|witness_index`
  (pipe-separated, no spaces; `pin_seq` and `witness_index` as decimal text)

The witness ledger is the emit-mode mirror of the pass chain: forecast/eval
append to `pass_chain.jsonl` and never to `emit_witness.jsonl`; emit appends to
`emit_witness.jsonl` and never to `pass_chain.jsonl`. Repeated emits under
unchanged state keep the plaque byte-stable while the witness ledger grows.

Do not merge ridge_lambda into the OLS Gram matrix. Do not stamp wall-clock
timestamps into plaque, seal, or witness JSON. CRC-style rolling hashes are out
of scope — use SHA-256 file digests only.
