# Edgekiln CLI

```
/app/bin/cdnqual run-forge --wire /app/polbay/run_manifest.json
```

Behavior:

1. Read the wire JSON object with keys `policy`, `capture_root`, `labels`, `out_dir`.
2. If environment variable `CDNQUAL_CAPTURE_ROOT` is non-empty, replace `capture_root` with that absolute path.
3. Load policy JSON from `policy`.
4. Discover `*.pcap` files directly under `capture_root` (non-recursive), sort by basename.
5. Load labels JSONL from `labels`.
6. Run the kiln pipeline and write artifacts into `out_dir` (create directory if needed).

## Rebuild helper

The image includes /app/scripts/rebuild-cdnqual.sh (also linked as /usr/local/bin/rebuild-cdnqual) to refresh /app/bin/cdnqual after Go source edits. Any approach that leaves a working /app/bin/cdnqual is acceptable as long as run-forge behavior matches this contract.
