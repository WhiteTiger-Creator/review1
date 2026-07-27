# Export shapes

Artifacts are written under `/app/output` (override with `OUTPUT_DIR`).

## binding_transcript.json

Array of objects:

| field | type | meaning |
|-------|------|---------|
| slot_ref | string | logical socket ref name |
| policy_epoch | uint64 | monotonic generation per slot_ref |
| path_digest_hex | string | first 32 hex chars of sha256 over path bytes |

For a fixed configured path string, `path_digest_hex` is stable across cycles.
Each rematerialization in probe order must publish a distinct `bind_cookie` whose
generation matches the listener inode generation for that cycle.

## auth_trace.json

Array of objects:

| field | type | meaning |
|-------|------|---------|
| slot_ref | string | logical socket ref name |
| mark_digest_hex | string | first 16 hex chars of sha256 over `tag:uid` |
| seal_hex | string | lane fingerprint from the peer model |
| supp_mask | uint32 | supplemental mask after transition rules |
| policy_epoch | uint64 | generation stamp |
| bind_cookie | string | live listener bind cookie |

## probe_report.jsonl

One JSON object per line:

| field | type | meaning |
|-------|------|---------|
| slot_ref | string | ref probed |
| cred_gap | int | current_uid - pinned_uid |
| pinned_uid | int | pinned view uid from the live-cookie vault sample |
| current_uid | int | current view uid from the authorization facet |
| seal_match | int | 1 when vault sample and facet agree under the live cookie |
| bind_cookie | string | live listener bind cookie |

Sibling `slot_ref` lines pin that ref's live-cookie vault sample against the
active authorization facet; equal uids with different lane fingerprints keep
`seal_match` at 0.

## auth_journal.jsonl

One JSON object per line with fields `op`, `slot_ref`, `mark`, `seal_hex`,
`supp_mask`, `policy_epoch`, and `bind_cookie`. Ops are `intake` and `rebind`.

## converge_report.json

```json
{ "cycles": [ { "cycle": 0, "scope_agreement_count": N, "transcript_rows": T, "trace_rows": R, "journal_rows": J } ] }
```

The last cycle must report `scope_agreement_count` of at least 3.
