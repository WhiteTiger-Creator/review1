# Edgekiln invariants

1. Re-running `run-forge` with the same wire map and env overrides must rewrite identical bytes for all four qualitycast artifacts.
2. Changing `ridge_lambda` in the policy must change `w_milli` and therefore `weights_sha256`.
3. Prefer-newest overlap must change reassembled payload versus first-write-wins on the overlap-bearing public bout (`bout_overlap`).
4. Out-of-order public bout (`bout_ooo`) must report `out_of_order_count >= 1`.
5. Retransmit public bout (`bout_rexmit`) must report `retransmit_count >= 1`.
6. `specterlure` must stay unlinked from the cast binary import graph.

## Checkpoint mirror

Export stage also writes /app/qualitycast/checkpoint/eval_ledger.snap.json as a byte-identical checkpoint mirror of eval_ledger.json for rerun checks.

