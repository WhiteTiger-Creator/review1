# Database compatibility

Credential store deployments must preserve generation-scoped ciphertext, deterministic nonce allocation, and reader snapshot authority across rotation and recovery.

| Version | Description |
|---:|---|
| 1 | Legacy flat `legacy_records` table with `(version_epoch, version_counter)` tuples |
| 2 | Intermediate `records` table with generation support |
| 3 | Current schema with generation catalog, upgrade journal, reader pins, and nonce reservations |

Supported legacy versions are listed in `config/service.toml` under `supported_legacy_versions`.

## Record version semantics

Logical record identity is `record_id`. Record history within a generation is ordered by canonical version `(version_epoch, version_counter)` compared lexicographically — epoch first, then counter. Counter-only comparison is incorrect for v1 databases where epoch ordering differs from counter ordering.

## Legacy import

`opsctl import-legacy --source <path>` supports schema versions 1 and 2.

- A nonexistent (fresh) target database is supported.
- An already initialized but logically empty current-schema target is supported: schema version 3 is present, generation 1 exists, and there are no credential rows and no active upgrade journal. In that case the existing generation 1 catalog row must be updated in place; importing must not fail with a unique-constraint violation on `generation_catalog`.
- Versions of the same `record_id` are compared lexicographically by `(version_epoch, version_counter)`. Source row order must not change which version wins; for example `(1, 1)` is newer than `(0, 5)`.
- The source is validated before any target mutation. Unsupported schema versions and malformed source schemas fail nonzero without partially modifying the target.
- Import into a non-empty target (any existing credential rows) or a target with an active upgrade is rejected atomically; the target database must remain unchanged (no partial schema rewrite, catalog churn, or row edits).
- Successful imports commit atomically in a single transaction.

## Generation states

`generation_catalog.state` values:

- `copying`
- `validated`
- `published`
- `pins_reconciled`
- `cleanup_pending`
- `complete`

`published` and `pins_reconciled` are distinct states. A generation marked `published` may still require pin reconciliation before cleanup.

## Nonce uniqueness

Within one generation, committed ciphertext rows must not share the same `(key_id, nonce)` pair. The requirement is not global across unrelated generations. Nonce values are allocated deterministically from `(key_id, generation_id, reservation_sequence, slot)`, so the generation id is part of the allocation identity. Legacy sources and in-flight source generations may contain nonce values that also appear in another generation; that alone is not a duplicate committed pair.

Enforce generation-local uniqueness in application logic (commit, validation, and recovery rejection), not with SQLite `UNIQUE` indexes on `(key_id, nonce)` or `(generation_id, key_id, nonce)`. The schema intentionally omits such indexes so recovery can detect and reject duplicate committed pairs already present in corrupt state.

### Ordinary credential writes

`opsctl put` commits ciphertext under the active generation using the same deterministic nonce scheme:

```text
(key_id, generation_id, reservation_sequence, slot)
```

For ordinary writes, `reservation_sequence` is `0`. The `slot` must uniquely identify each committed row within that generation.

Do not derive the slot from record version metadata alone. Multiple distinct `record_id` values can each begin at `(version_epoch, version_counter) = (0, 1)`; assigning the same slot to those unrelated first-time writes produces identical `(key_id, nonce)` pairs and violates generation-local uniqueness before any rotation occurs.

A practical invariant: after seeding or writing `N` distinct records in one generation, that generation must contain `N` distinct committed `(key_id, nonce)` pairs.

Committed-row uniqueness and reservation exhaustion are different invariants. Validation concerns the nonce pairs actually attached to committed target rows, not whether every reserved slot was consumed. Unused reservation slots do not invalidate an otherwise complete target; they may be retired after copying completes. Every copied committed target occurrence must have exactly one matching consumed reservation with the same `key_id`, `nonce`, and `record_id` under the active `upgrade_id`; orphaned consumed reservations, duplicate funding, and reservations owned by a different upgrade are invalid. A reservation from a completed earlier rotation cannot fund a committed row in the active target generation. See `/app/docs/generation-handoff.md` for copy identity, reservation batch rollover, committed-row accounting, reservation provenance, batch continuation, validation boundary, and successive rotation rules. No global uniqueness constraint may be applied across generations or legacy source rows.

## Cleanup eligibility

A generation may be removed only when all of the following hold:

- no active durable reader pin references it, and
- no unfinished upgrade journal lists it as `source_generation_id` or `target_generation_id`, and
- it is not the published generation for new readers, and
- it is not the newest generation present in `generation_catalog`

Do not treat “missing published generation” or “no published row yet” as a reason to skip the journal-dependency check. An unfinished journal retains both its source and target generations until the journal reaches `complete`.

## Ordinary reads vs pinned reads

Ordinary current reads (`opsctl get` / HTTP GET without a reader token) consult only the currently published generation. If the record is absent there, the read fails as not found — they must not search older generations. Reader-token reads continue to use exactly the generation stored in that token.

## Malformed recovery

Recovery on incompatible or malformed journal/catalog combinations must return a nonzero exit code and leave the database file and audit log unchanged. This includes missing target generations, reservation accounting mismatches, duplicate committed nonce pairs within a generation, cross-upgrade reservation aliasing, and cursor positions that skip required source occurrences. Atomic rejection means database files, WAL/SHM sidecars, and audit bytes are byte-for-byte identical before and after a failed recovery attempt.

## Status and inspect output

`opsctl status --json` returns a JSON object with:

- `database_path`, `schema_version`
- `current_generation`, `published_generation`
- `upgrade_phase`, `upgrade_id`
- `active_reader_count`
- `generation_states[]` with `generation_id`, `state`, `key_id`, `record_count`

Audit JSONL records include `timestamp`, `operation`, `upgrade_id`, `phase`, `outcome`, `source_generation`, `target_generation`, `reader_count`, and `reason_code`.

`opsctl inspect --json` returns generation summaries, journal summary, pin list, and nonce reservation count. It does not expose raw encryption keys.
