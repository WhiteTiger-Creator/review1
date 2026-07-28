# Eval staging contract

`wtac-validate eval --campaign-dir DIR --work-dir DIR` requires a prior `feature` run in the same work directory.

Eval must:

1. Load `feature_batch.json` from the work directory (fail if missing).
2. Verify `campaign_id` matches the campaign `conditions.json`.
3. Use staged `q_inf_pa`, `pairs`, and `alpha_rad` as the sole inputs to pressure-path model inference (do not recompute freestream q or Cp pairs from raw campaign JSON for the pressure path).
4. Convert staged `alpha_rad` to degrees only when calling APIs that still accept degrees (`alpha_deg = alpha_rad * 180 / pi`).
5. Still load tare runs and balance labels from the campaign directory for label-path metrics.
6. On success, increment `eval_count` in `feature_ledger.json` only when `feature_epoch` matches the staged batch.

Recomputing pressure-path features from raw campaign inputs during eval is a contract violation even if numeric results coincidentally match public fixtures.
