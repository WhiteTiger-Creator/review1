# Operations

The consumer trust desk loads `/app/data/scenario_pack.json` and the corpus tree under `/app/data/`. Supporting tables also live under `/app/data/` (anchors and cache subtrees). Treat those files as runtime inputs the desk already knows how to open — do not assume every file under `/app/data/` participates in every decision.

Local probe (`scripts/local_probe.sh`) only checks signer-view marks on demo corpus rows. That CLEAN signal is not consumer trust authorization. Federation trust outcomes come from `/app/bin/trust_desk` after `scripts/build.sh`.

Several packages under `/app` expose helpers used by logs, probes, or unused legacy paths. Rebuild before comparing trust digests; hand-edited JSON under `/app/output` will not survive a fresh authorization run.

## Cutover notes

When a window-table slot has `dual` set, consumer authorization treats generations equal to `a` or `b` as live for that slot. The `legacy` and `tip` fields remain on the row for ledger bookkeeping and single-tip operation; they are not the dual-window live set. Once `dual` clears, only `tip` is live, and generations recorded in the revoke ledger must not authorize.
