# Report schema

Write UTF-8 JSON to the absolute `--output` path.

Serialization:

* two-space indentation
* typed field order as below
* one trailing newline
* no trailing spaces

Top-level keys, in this exact order:

1. `assertion_rows`
2. `credential_rows`
3. `challenge_rows`
4. `summary`

Atomic replace through one sibling temporary file next to the output path.

## `assertion_rows`

Include every processed assertion result stored in the database (not future pending jobs).

Sort by: `received_at`, then `assertion_id`.

Fields, in this exact order:

| Field | JSON type |
| --- | --- |
| `assertion_id` | string |
| `credential_id` | string |
| `challenge_id` | string |
| `received_at` | string |
| `status` | string (`accepted` \| `rejected`) |
| `reason_or_null` | string or null |
| `risk_or_null` | string or null |
| `user_present_or_null` | integer `0`/`1` or null |
| `user_verified_or_null` | integer `0`/`1` or null |
| `backup_eligible_or_null` | integer `0`/`1` or null |
| `backup_state_or_null` | integer `0`/`1` or null |
| `sign_count_or_null` | integer or null |
| `sign_count_before_or_null` | integer or null |
| `sign_count_after_or_null` | integer or null |
| `challenge_consumed` | integer `0`/`1` |
| `credential_mutated` | integer `0`/`1` |

## `credential_rows`

Include every credential. Do not expose public keys.

Sort by: `rp_id`, then `user_id`, then `credential_id`.

Fields, in this exact order:

| Field | JSON type |
| --- | --- |
| `credential_id` | string |
| `user_id` | string |
| `rp_id` | string |
| `status` | string |
| `sign_count` | integer |
| `backup_eligible` | integer `0`/`1` |
| `backup_state` | integer `0`/`1` |
| `last_used_at_or_null` | string or null |

## `challenge_rows`

Include every challenge.

Sort by: `rp_id`, then `challenge_id`.

Fields, in this exact order:

| Field | JSON type |
| --- | --- |
| `challenge_id` | string |
| `rp_id` | string |
| `status` | string (`consumed` \| `expired` \| `available`) |
| `issued_at` | string |
| `expires_at` | string |
| `consumed_at_or_null` | string or null |
| `consumed_by_assertion_id_or_null` | string or null |

Challenge report status at the requested as-of instant:

* `consumed`: `consumed_at` is non-null
* `expired`: unconsumed and `expires_at < as_of`
* `available`: unconsumed and `expires_at >= as_of`

## `summary`

Fields, in this exact order:

| Field | Meaning |
| --- | --- |
| `processed_assertion_count` | number of assertion rows |
| `accepted_assertion_count` | assertion rows with status `accepted` |
| `rejected_assertion_count` | assertion rows with status `rejected` |
| `risk_assertion_count` | assertion rows with non-null `risk_or_null` |
| `consumed_challenge_count` | challenge rows with status `consumed` |
| `active_credential_count` | credentials with status `active` |
| `quarantined_credential_count` | credentials with status `quarantined` |
| `revoked_credential_count` | credentials with status `revoked` |
| `pending_future_job_count` | jobs still `pending` after the run (including future ignored jobs) |
