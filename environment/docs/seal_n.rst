Eval seal and lineage (seal_n)

Durable eval seal path: `/app/var/psr/eval_seal.json`.

Seal members:

* `stage` (string): `OPEN` while scoring, `COMMIT` after promotion.
* `gen` (integer): active lineage generation, starting at 1.
* `eval_fp` (string): 8-hex fingerprint of the current evaluation pack tree.
* `bind_hex` (string): 8-hex bind over promoted observation digests.

Evaluation fingerprint. Walk every `*.json` under `<root>/fixtures` in
lexicographic path order (relative to `<root>`). For each file, fold the raw
UTF-8 bytes into an FNV-1a 32-bit state (offset basis 2166136261, prime
16777619). Emit eight lowercase hex digits. Changing any pack byte must change
`eval_fp`.

Generation authority. Before scoring, the evaluate driver opens the seal to
stage `OPEN`. If a prior `COMMIT` seal exists whose `eval_fp` equals the current
fingerprint, reuse that seal's `gen`. Otherwise set `gen` to prior `gen + 1`, or
to 1 when no prior seal exists. Partial `OPEN` seals are never authoritative for
reuse.

Promotion. After both observation roots are written, compute `bind_hex` by
FNV-1a mixing, in order: UTF-8 bytes of primary `band_digest`, hold
`band_digest`, primary `q_digest`, hold `q_digest`, then `eval_fp` UTF-8 bytes,
then little-endian bytes of `gen` as uint64. Emit eight lowercase hex digits.
Write stage `COMMIT`, then finish.

Observation roots and rights sheet. Every `/app/output/obs_primary.json`,
`/app/output/obs_hold.json`, and `/app/output/rights_map.json` must carry the
same integer `gen` and the same `eval_fp` string as the COMMIT seal.

Eval ledger. The evaluate driver truncates `/app/run/psr_ledger.jsonl` at start,
then appends one JSON object per channel with keys `sid`, `root`, `bands`,
`cls`, `q`, `fld`, `gen`, `eval_fp`.

Recover. `/app/environment/recover_k4.sh` rebuilds the four scored artifacts
under `/app/output` from `/app/run/psr_ledger.jsonl` alone when the seal is
`COMMIT`, `eval_fp` matches the live fixture tree under `/app/environment`, and
every ledger line shares that `gen` and `eval_fp`. Recover must refuse
(non-zero exit) when the seal is missing, `OPEN`, fingerprint-mismatched, or
generation-mismatched against the ledger. Recover must not re-run inference
from `fixtures/` packs.

Newer live fingerprints always win over a recovered older generation: after a
pack edit, evaluate must bump `gen` and reseal rather than keep a stale COMMIT.
