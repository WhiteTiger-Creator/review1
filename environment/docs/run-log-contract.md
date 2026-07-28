# Run log

Path: `/app/state/run_log.jsonl`

One JSON object per line. Stage order for a compliant forecast/eval pass
(rewritten each forecast/eval; not appended across redrives):

design, vault, latch_pin, beta, commit, seal, forecast, trust, plaque

Each line includes `stage` and `ok`. Stage tokens are exactly those eight names
plus `seal` — not the on-disk filenames (`fit_commit`, `emit_trust`,
`beta_latch_seal`).

Vault-only mode must not write this file. Pass-chain append semantics live in
`/app/docs/pass-chain-contract.md` (separate artifact).
