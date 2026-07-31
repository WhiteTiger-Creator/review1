# Eval ledger contract

Write `/app/qualitycast/eval_ledger.json`:

```json
{
  "schema": "cdnqual.ledger.v1",
  "bout_count": <int>,
  "train_count": <int>,
  "accuracy_milli": <int>,
  "mean_abs_err_milli": <int>,
  "payload_hash": "<sha256 hex of concatenated bout payloads in bout_id order>",
  "policy_lambda": <int>,
  "capture_root": "<resolved absolute capture root>",
  "predictions": [
    {"bout_id": "...", "y": 0, "yhat": 1, "score_milli": 123}
  ]
}
```

Definitions:

- Evaluate every bout present in the active capture bank that also has a label.
- `accuracy_milli = floor(1000 * correct / N)`.
- `mean_abs_err_milli = floor(1000 * mean(|y - s|))` where `s` is the float score before thresholding.
- `predictions` sorted by `bout_id` ascending.
- `payload_hash`: SHA-256 over `client_payload || server_payload` for each bout in `bout_id` order, concatenated (no delimiters).
