# Attestation payload

Each hall row is sealed over a canonical JSON payload built from that row's
published counters. The payload is a two-key object:

```
{"name": <hall name>, "stats": { ...counters... }}
```

`stats` carries exactly these keys, in ascending key order:

```
approval_blocks
capacity_trims
certified_count
compute_blocks
maintenance_blocks
network_blocks
rack_count
readiness_index
region_rejections
storage_blocks
```

The payload is serialized as compact JSON with no whitespace between tokens
and no trailing newline, then hashed with sha256 and rendered as lowercase
hexadecimal. `attestation` itself is never part of the payload.

The programme-level value is sha256 over the per-hall attestations sorted
ascending as strings and joined with a single `|` separator.
