# Export Ledger

/app/state/export-ledger.json tracks export history.

## Structure

- exports: array of export entry objects

## Export Entry

- staging_hash: hash of the staging data used for this export
- export_fingerprint: SHA-256 of the exported shunting-sequence.json content
- exported_at: ISO-8601 timestamp

## Append semantics

Every successful export appends one new entry to the exports array. Do not overwrite the array, replace prior entries, or deduplicate by staging_hash or export_fingerprint. Two full pipeline runs that produce identical fingerprints still yield at least two ledger entries.

## Fingerprint stability (not ledger idempotency)

Re-running export on unchanged validated output must produce the same export_fingerprint string. The fingerprint is a SHA-256 hex digest of the full content of the file at /app/output/shunting-sequence.json (the complete sequence document). Byte-stable fingerprints describe that digest only. They do not authorize skipping an append or collapsing the ledger to a single row.

If the export-ledger.json already contains an entry with a non-empty export_fingerprint and the staging inputs have not changed, re-ingesting must preserve the same staging_hash.
