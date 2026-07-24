# Report schema

`reconcile --trace TRACE --output OUTPUT` writes an authority report JSON document.

## Required fields

| Field | Type | Meaning |
| --- | --- | --- |
| `scenario` | string | Manifest scenario (`ops-seal`) |
| `manifest_generation` | int | Live verified generation |
| `manifest_digest` | string | SHA-256 hex of exact installed manifest bytes |
| `authority_sound` | bool | True only when invariants hold and `violations` is empty |
| `violations` | string[] | Independently detected integrity problems |
| `requests_seen` | int | Distinct request ids observed in decisions |
| `committed_requests` | int | Allow decisions |
| `denied_requests` | int | Deny decisions |
| `pending_requests` | int | Prepared work without terminal commit/deny/recovery_denied |
| `conflict_requests` | int | Conflict decisions |
| `effects_applied` | int | Effect ledger rows |
| `helpers_trusted` | bool | Live helpers verify against the signed manifest |
| `recovery_complete` | bool | No unresolved pending work |
| `idempotency_sound` | bool | No duplicate effects for the same request identity |
| `journal` | string | Path to journal JSONL |
| `decision_log` | string | Path to decisions JSONL |
| `effect_log` | string | Path to effects JSONL |
| `manifest` | string | Path to installed manifest |
| `trace` | string | Path to reconcile trace JSONL |
| `ledger_digest` | string | Deterministic seal over live ledgers |

Numeric fields are derived from live evidence. They are not fixed constants.

## Ledger digest

`ledger_digest` is SHA-256 (lowercase hex) over compact JSON with sorted object keys:

```json
{"decisions":[...],"effects":[...],"journal":[...]}
```

Each array is the corresponding JSONL records sorted by `seq` / `event_seq`. Encoding uses standard compact JSON (`encoding/json` map key sort / no insignificant whitespace).

## Authority soundness

`authority_sound` is true only when:

- the installed manifest signature and digest verify
- live helpers verify (path, type, mode, digest)
- violations is empty
- helpers_trusted, recovery_complete, and idempotency_sound are true

Reconcile must detect at least: orphan effects, duplicate effects, mismatched digests/generations/helpers/actions/units/outcomes, body substitution, unresolved prepared work, and journal order contradictions. It must not trust stored booleans without recomputation.
