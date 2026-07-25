# Staging Schema

/app/state/yard-staging.json captures the complete ingest state.

## Fields

- train_id: from consist.json
- staged_at: ISO-8601 timestamp of ingest
- topology: full topology object from topology.json
- consist: the cars array from consist.json (not the whole consist.json object; not a wrapper that adds extra keys)
- plan: full plan object from plan.json
- failures: full failures object from failures.json
- staging_hash: SHA-256 hex digest described below

## staging_hash input (exact)

Hash exactly these five top-level keys and no others:

- train_id
- topology
- consist (cars array only)
- plan
- failures

Exclude staged_at and staging_hash from the hashed object. Do not add helper fields such as staged_at, car_count, or yard_dir into the hashed body.

Serialize with compact JSON and recursively sorted keys at every nesting level: separators must be comma and colon with no spaces, equivalent to sort_keys true and separators (',', ':'). Indented or pretty-printed JSON must not be used as the hash input. Digested bytes are the UTF-8 encoding of that compact string; staging_hash is the lowercase hex SHA-256 of those bytes.

## Stability

Re-running ingest on unchanged inputs must produce the same staging_hash, because the hash excludes staged_at.
