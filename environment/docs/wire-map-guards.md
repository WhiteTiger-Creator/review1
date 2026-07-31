# Absolute wire guards

`run_manifest.json` fields:

| Key | Meaning |
|-----|---------|
| `policy` | Absolute path to `cdn_policy.json` |
| `capture_root` | Absolute directory of `*.pcap` files |
| `labels` | Absolute path to labels JSONL |
| `out_dir` | Absolute output directory (default `/app/qualitycast`) |

Policy fields:

| Key | Type | Meaning |
|-----|------|---------|
| `ridge_lambda` | int | L2 penalty `λ` (≥ 1) |
| `feature_dim` | int | must be `12` |
| `score_threshold_milli` | int | must be `500` (0.5) |
| `schema` | string | `cdnqual.policy.v1` |

Refuse to run when `feature_dim != 12` or `schema` mismatches.
