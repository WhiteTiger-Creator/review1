# Staging Schema

/app/state/yard-staging.json captures the complete ingest state.

## Fields

- train_id: from consist.json
- staged_at: ISO-8601 timestamp of ingest
- topology: full topology object from topology.json
- consist: full cars array from consist.json
- plan: full plan object from plan.json
- failures: full failures object from failures.json
- staging_hash: SHA-256 hex digest of the canonical compact JSON representation of the staging body (all fields except staging_hash and staged_at, with keys sorted recursively)

## Stability

Re-running ingest on unchanged inputs must produce the same staging_hash, because the hash excludes staged_at. The hash uses canonical JSON: compact format with keys sorted at every nesting level.
