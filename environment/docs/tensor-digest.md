# Feature digest contract

Write `/app/qualitycast/feature_digest.json`:

```json
{
  "schema": "cdnqual.digest.v1",
  "features_sha256": "<sha256 of session_features.jsonl raw bytes>",
  "weights_sha256": "<sha256 of ridge_weights.json raw bytes>",
  "ledger_sha256": "<sha256 of eval_ledger.json raw bytes>",
  "bout_ids": ["..."],
  "feature_row_count": <int>
}
```

`session_features.jsonl` must use LF newlines, one JSON object per line, no trailing spaces, and a final newline after the last row.
JSON objects in weights/ledger/digest use compact encoding: keys in the schemas' listed order, no extra whitespace except the required final newline on JSONL only. For JSON files use standard library compact marshal with sorted struct order as specified by Go `encoding/json` on the exported structs documented here — field order must match the schemas exactly as listed.
