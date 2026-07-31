# Sealed yard map

Graders stage an alternate capture directory and may set:

CDNQUAL_CAPTURE_ROOT=/opt/verifier-fixtures/hidden
CDNQUAL_LABELS=/opt/verifier-fixtures/hidden_labels.jsonl

Public fixture files under the verifier fixtures root include:

- public_session_features.jsonl
- public_ridge_weights.json
- public_eval_ledger.json
- public_feature_digest.json

Hidden fixture files under the verifier fixtures root include:

- hidden_labels.jsonl
- hidden_session_features.jsonl
- hidden_ridge_weights.json
- hidden_eval_ledger.json
- hidden_feature_digest.json
- holdout_floors.json with keys min_bout_count, min_accuracy_milli, expected_bout_ids
- perturbation_refs.json with keys public_weights_sha256, lambda7_weights_sha256

Public bank bout ids include bout_clean, bout_ooo, bout_rexmit, bout_overlap, bout_gap, and bout_long.
Hidden bout ids use the disjoint hz_* prefix: hz_alpha, hz_bravo, hz_charlie, hz_delta (listed in expected_bout_ids).
