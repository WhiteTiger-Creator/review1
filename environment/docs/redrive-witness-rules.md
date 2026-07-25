# Redrive and witness rules

Successful forecast/eval passes are idempotent under unchanged traces: stage
artifact bytes stay fixed while `pass_chain.jsonl` grows. Operators treat each
pass-chain line as a witness of the prior seal/tape binding.

Do not merge ridge_lambda into the OLS Gram matrix. Do not stamp wall-clock
timestamps into plaque or seal JSON. CRC-style rolling hashes are out of scope —
use SHA-256 file digests only.
