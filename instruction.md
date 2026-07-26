The chironym desk under `/app/environment` must score frozen sign-language translation hypotheses. It must run a one-pass pairwise-pull gloss-token embedding update on train-fold index pairs, score each hyp/gold gloss pair with soft-DTW using the learned embeddings, calibrate a temperature on calib-fold scores, and choose a confidence threshold for selective prediction under the documented risk/coverage contract. Normative formulas, digests, epoch/memo rules, schemas, and negative-path text are in `/app/environment/docs/contracts.md`. CLI rules are in `/app/environment/docs/cli.md`. Build steps are in `/app/environment/docs/toolchain.md`.

Complete the desk so evaluate produces contract-faithful embeddings, soft-DTW quality scores, calibrated temperatures, risk-target thresholds, calib/eval coverage and risk, and cross-artifact agreement among JSON, CSV, log, campaign state, history, ledger, and CLI lines—including under pack or policy mutations for the same campaign id, repeated evaluate calls, and invalid-campaign fail-closed behavior.

Rebuild binaries per `/app/environment/docs/toolchain.md` (including cargo target dirs under `/tmp/chironym_vbin/target_k7` and `/tmp/chironym_vbin/target_m3`, installing `/tmp/chironym_vbin/target_k7/release/k7` and `/tmp/chironym_vbin/target_m3/release/m3`). Prepare the output directory, then run evaluate. The verifier clears `/app/output`, may reset `/app/var`, rebuilds from source, and mutates campaign inputs; static artifact drops under `/app/output` are insufficient.

Default successful path:

```bash
/app/bin/chironymctl prepare --output /app/output
/app/bin/chironymctl evaluate --campaign /app/environment/data/campaigns/studio_a --output /app/output
```

Successful evaluate must write `/app/output/align_report.json`, `/app/output/utterance_scores.csv`, `/app/output/eval_summary.log`, `/app/output/campaign_state.json`, and `/app/output/risk_history.jsonl`, print `TOP_ACCEPT_RATE=`, `BUNDLE_DIGEST=`, and `EPOCH=` lines, and append one success row to `/app/var/chironym_ledger.json`. Unprepared evaluate must fail with stderr beginning `chironym output not armed:`. Invalid campaigns must exit non-zero with stderr beginning `invalid chironym campaign:` without appending a success ledger row. Verification may copy campaigns under `/app/output/scratch_a`, `/app/output/scratch_b`, `/app/output/scratch_mut`, and `/app/output/scratch_bad` for mutation and invalid-input cases, and may also exercise `/app/environment/fixtures/studio_b`. The verifier rebuilds learner binaries under `/tmp/chironym_vbin`.
