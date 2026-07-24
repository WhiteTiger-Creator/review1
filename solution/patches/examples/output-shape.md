# Expected output shape

The `synthesize` command writes three artifacts into the output directory:

1. `build-plan.json` — format `aurora-build-plan-v3`
2. `dependency-lock.json` — format `aurora-dependency-lock-v1`
3. `ffmpeg.mk` — GNU Make rules with `ASSET_ROOT`, `OUTPUT_ROOT`, `CACHE_ROOT`, `FFMPEG`

Jobs are ordered by `job_id`. Filter nodes carry `phase` and `sequence` and preserve duplicates.
