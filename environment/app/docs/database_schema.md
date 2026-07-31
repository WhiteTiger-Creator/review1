# Database schema

SQLite relying-party authentication audit store for the bounded WebAuthn
assertion security profile. Enable `PRAGMA foreign_keys = ON`. Do not enable
`read_uncommitted` or shared-cache dirty reads.

Unknown additional tables may be ignored. Unknown columns on required tables may be ignored.
All required tables and columns must exist with compatible declared types.

## `schema_metadata`

Exactly one row.

| Column | Type | Constraints |
| --- | --- | --- |
| `schema_version` | INTEGER NOT NULL | must equal `1` |

## `rp_policies`

| Column | Type | Constraints |
| --- | --- | --- |
| `rp_id` | TEXT | PRIMARY KEY |
| `require_user_verification` | INTEGER NOT NULL | exactly `0` or `1` |
| `backup_counter_policy` | TEXT NOT NULL | `strict` or `backup_aware` |

### Policy meaning

* `strict`: every non-increasing nonzero counter is rejected; credential is quarantined.
* `backup_aware`: a non-increasing nonzero counter for a **backup-eligible** credential is accepted with risk `non_monotonic_backup_counter`; stored counter never decreases. Does **not** relax counter rules for non-backup-eligible credentials.

## `rp_origins`

| Column | Type | Constraints |
| --- | --- | --- |
| `rp_id` | TEXT NOT NULL | references `rp_policies(rp_id)` |
| `origin` | TEXT NOT NULL | |
| PRIMARY KEY | (`rp_id`, `origin`) | |

Origin comparison is exact Unicode string equality after successful JSON decoding.
No wildcard origins, suffix matching, default-port removal, or URL rewriting.

## `users`

| Column | Type | Constraints |
| --- | --- | --- |
| `user_id` | TEXT | PRIMARY KEY |
| `status` | TEXT NOT NULL | `active` or `disabled` |

## `credentials`

| Column | Type | Constraints |
| --- | --- | --- |
| `credential_id` | TEXT | PRIMARY KEY |
| `user_id` | TEXT NOT NULL | references `users(user_id)` |
| `rp_id` | TEXT NOT NULL | references `rp_policies(rp_id)` |
| `public_key_sec1` | BLOB NOT NULL | exactly 65 bytes; first byte `0x04` |
| `sign_count` | INTEGER NOT NULL | `0..4294967295` |
| `backup_eligible` | INTEGER NOT NULL | `0` or `1` |
| `backup_state` | INTEGER NOT NULL | `0` or `1`; if `1` then `backup_eligible` must be `1` |
| `status` | TEXT NOT NULL | `active`, `quarantined`, or `revoked` |
| `last_used_at` | TEXT NULL | RFC 3339 UTC `YYYY-MM-DDTHH:MM:SSZ` when set |

## `challenges`

| Column | Type | Constraints |
| --- | --- | --- |
| `challenge_id` | TEXT | PRIMARY KEY |
| `rp_id` | TEXT NOT NULL | references `rp_policies(rp_id)` |
| `challenge_bytes` | BLOB NOT NULL | length `16..64` |
| `issued_at` | TEXT NOT NULL | RFC 3339 UTC profile |
| `expires_at` | TEXT NOT NULL | RFC 3339 UTC profile; `issued_at <= expires_at` |
| `consumed_at` | TEXT NULL | both null or both non-null with `consumed_by_assertion_id` |
| `consumed_by_assertion_id` | TEXT NULL | both null or both non-null with `consumed_at` |

## `assertion_jobs`

| Column | Type | Constraints |
| --- | --- | --- |
| `assertion_id` | TEXT | PRIMARY KEY |
| `received_at` | TEXT NOT NULL | RFC 3339 UTC profile |
| `event_seq` | INTEGER NOT NULL | nonnegative signed 64-bit |
| `credential_id` | TEXT NOT NULL | |
| `challenge_id` | TEXT NOT NULL | |
| `client_data_json` | BLOB NOT NULL | original client bytes |
| `authenticator_data` | BLOB NOT NULL | |
| `signature_der` | BLOB NOT NULL | |
| `status` | TEXT NOT NULL | `pending` or `processed` |

No foreign key from pending jobs to credentials or challenges is required; unknown identities are request-level rejections.

## `assertion_results`

| Column | Type | Constraints |
| --- | --- | --- |
| `assertion_id` | TEXT | PRIMARY KEY |
| `status` | TEXT NOT NULL | `accepted` or `rejected` |
| `reason_or_null` | TEXT NULL | null when accepted; otherwise a published reason token |
| `risk_or_null` | TEXT NULL | normally null; accepted risk `non_monotonic_backup_counter` only |
| `credential_id` | TEXT NOT NULL | |
| `challenge_id` | TEXT NOT NULL | |
| `received_at` | TEXT NOT NULL | |
| `user_present_or_null` | INTEGER NULL | `0`/`1` when authenticator data was parsed |
| `user_verified_or_null` | INTEGER NULL | `0`/`1` when authenticator data was parsed |
| `backup_eligible_or_null` | INTEGER NULL | `0`/`1` when authenticator data was parsed |
| `backup_state_or_null` | INTEGER NULL | `0`/`1` when authenticator data was parsed |
| `sign_count_or_null` | INTEGER NULL | received counter when authenticator data was parsed |
| `sign_count_before_or_null` | INTEGER NULL | live stored credential counter immediately before this assertion |
| `sign_count_after_or_null` | INTEGER NULL | stored credential counter immediately after this assertion's mutation boundary |
| `challenge_consumed` | INTEGER NOT NULL | `0` or `1` |
| `credential_mutated` | INTEGER NOT NULL | `0` or `1` |

## Per-assertion state snapshots

Eligible assertions are processed sequentially in the published chronological
order inside one transaction.
`sign_count_before_or_null` is the stored credential `sign_count` immediately before
the current assertion, including mutations committed by earlier eligible
assertions in the same batch.
`sign_count_after_or_null` is the stored credential `sign_count` immediately after
applying the current assertion's documented mutation boundary.
These fields are not snapshots of the original fixture row.

Counter truth table for the live stored/received pair:

* `stored = 0`, `received = 0`:
  accept as unsupported counter; after = 0; risk = null
* `received > stored`:
  accept advancement; after = received; risk = null
* `received <= stored` and at least one value is nonzero:
  * strict policy or non-backup-eligible credential:
    reject replay; quarantine; count unchanged
  * `backup_aware` policy and backup-eligible credential:
    accept; risk = `non_monotonic_backup_counter`;
    after = `max(stored, received)`

`stored > 0` and `received = 0` is a non-increasing nonzero case.
It is not the unsupported-counter case.

## Whole-database preflight

Before mutation, validate required schema and persistent-state invariants. Fatal conditions include missing required tables/columns, schema version ≠ 1, invalid enums/booleans/timestamps, invalid public keys, counter out of u32 range, BS set while BE clear in stored credential state, broken required foreign keys, disagreeing challenge consumed fields, `issued_at` later than `expires_at`, assertion result for a pending job, and processed job without a result.

On whole-run fatal input: no database row changes; remove stale and temporary output; nonzero exit; nonempty stderr.
