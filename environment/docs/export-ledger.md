# Export Ledger

/app/state/export-ledger.json tracks export history.

## Structure

- exports: array of export entry objects

## Export Entry

- staging_hash: hash of the staging data used for this export
- export_fingerprint: SHA-256 of the exported shunting-sequence.json content
- exported_at: ISO-8601 timestamp

## Cross-Run Stability

Re-running export on unchanged validated output must produce the same export_fingerprint. The fingerprint is a SHA-256 hex digest of the full content of /app/output/shunting-sequence.json

If the export-ledger.json already contains an entry with a non-empty export_fingerprint and the staging inputs have not changed, re-ingesting must preserve the same staging_hash.
