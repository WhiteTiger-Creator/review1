# Bounded WebAuthn authentication-assertion audit profile

This document defines a **bounded WebAuthn authentication-assertion security profile**
for relying-party assertion verification and credential-state integrity. It is an
authentication-security contract: forged signatures, rebound challenges, origin
spoofing, RP ID hash mismatches, illegal flags, backup-eligibility mutations, and
clone-risk counters must fail closed with the published reasons.
It does not claim to reproduce every WebAuthn Level 3 or SQLite implementation detail.

## CLI

```text
webauthn-assertion-worker \
  --database /absolute/path/to/audit.sqlite \
  --as-of 2026-07-01T12:00:00Z \
  --output /absolute/path/to/report.json
```

* All three arguments are required.
* `--database` and `--output` must be absolute paths.
* `--as-of` must match `YYYY-MM-DDTHH:MM:SSZ` (UTC only, seconds required, no fractional seconds, no numeric offsets, valid calendar date/time). Compare parsed instants.
* Unknown CLI options are fatal.
* Output parent directory must already exist.
* Remove stale output before validation begins.
* Write through one sibling temporary path; remove it on fatal failure.
* Fatal failure: nonzero exit, nonempty stderr.
* Structurally valid input exits zero even when individual assertions reject.

## Cryptographic profile

* Credential type: `public-key`
* Algorithm: ES256 / COSE `-7`, NIST P-256
* Public key storage: 65-byte uncompressed SEC1 (`0x04 || X || Y`)
* Signature encoding: ASN.1 DER `Ecdsa-Sig-Value` only (reject raw 64-byte `r||s`, trailing bytes)
* Signed bytes: `authenticatorData || SHA-256(original clientDataJSON bytes)`
* Authenticator data length: exactly 37 bytes (no attested credential data, no extensions)

## Replay window and ordering

Eligible jobs:

* `status = "pending"`
* `received_at <= as_of` (inclusive)

Pending jobs with `received_at > as_of` are ignored completely (no result row, status stays pending, no challenge/credential mutation, absent from report assertion rows).

Process eligible jobs sorted by `received_at`, then numeric `event_seq`, then `assertion_id`.
Already processed jobs are never replayed. Same as-of rerun is idempotent and byte-identical.

## `clientDataJSON`

Treat stored bytes as the exact original sequence:

* valid UTF-8
* top-level JSON object
* required string fields: `type`, `challenge`, `origin`
* optional boolean `crossOrigin`
* unknown fields ignored
* reject duplicate relevant member names as `client_data_malformed`

Required values:

* `type = "webauthn.get"`
* `crossOrigin` absent or `false`
* `origin` exactly matches one `rp_origins` row for the credential RP
* `challenge` equals base64url **without padding** of `challenges.challenge_bytes`

Never parse-and-reserialize before hashing. Hash the original BLOB bytes.

## Authenticator data (37 bytes)

* bytes 0..31: `rpIdHash = SHA-256(UTF-8(rp_id))`
* byte 32: flags
* bytes 33..36: `signCount` unsigned big-endian u32

Supported flags: `UP=0x01`, `UV=0x04`, `BE=0x08`, `BS=0x10`.
Disallowed mask: `0xE2` (reserved `0x02`, reserved `0x20`, `AT=0x40`, `ED=0x80`).
Wrong length or disallowed bit → `authenticator_data_malformed`.
`BS` set while `BE` clear → `backup_flags_invalid` (after authentication boundary).

## First-failure precedence

Choose the first applicable reason in this exact order:

1. `credential_unknown`
2. `credential_inactive`
3. `challenge_unknown`
4. `client_data_malformed`
5. `client_data_type_invalid`
6. `authenticator_data_malformed`
7. `invalid_signature`
8. `challenge_not_yet_valid`
9. `challenge_expired`
10. `challenge_already_consumed`
11. `challenge_mismatch`
12. `origin_mismatch`
13. `cross_origin_disallowed`
14. `rp_id_hash_mismatch`
15. `user_presence_required`
16. `user_verification_required`
17. `backup_flags_invalid`
18. `backup_eligibility_changed`
19. `signature_counter_replay`

### Definitions

* `credential_unknown`: no credentials row for `credential_id`
* `credential_inactive`: credential `quarantined`/`revoked`, or owning user `disabled`
* `challenge_unknown`: no challenges row for `challenge_id`
* `client_data_malformed`: invalid UTF-8/JSON/top-level type, missing/wrong-typed required field, duplicate relevant key, or wrong-typed `crossOrigin`
* `client_data_type_invalid`: `type` is not `webauthn.get`
* `authenticator_data_malformed`: wrong length or disallowed flag bit
* `invalid_signature`: invalid public key, malformed DER, or failed ES256 verification
* `challenge_not_yet_valid`: `received_at < issued_at`
* `challenge_expired`: `received_at > expires_at` (equality is still valid)
* `challenge_already_consumed`: challenge already has consumed fields set
* `challenge_mismatch`: client challenge ≠ base64url-without-padding of challenge bytes, or challenge `rp_id` ≠ credential `rp_id`
* `origin_mismatch`: origin not in exact configured set for the RP
* `cross_origin_disallowed`: `crossOrigin` is true
* `rp_id_hash_mismatch`: first 32 authenticator-data bytes ≠ SHA-256(UTF-8(rp_id))
* `user_presence_required`: UP clear
* `user_verification_required`: RP requires UV and UV clear
* `backup_flags_invalid`: BS set while BE clear
* `backup_eligibility_changed`: assertion BE ≠ stored `backup_eligible`
* `signature_counter_replay`: bounded counter policy rejects non-increasing nonzero counter

Do not invent additional rejection tokens.

## Authentication and mutation boundaries

### Pre-authentication failures (no challenge consume, no credential mutate)

`credential_unknown`, `credential_inactive`, `challenge_unknown`,
`client_data_malformed`, `client_data_type_invalid`, `authenticator_data_malformed`,
`invalid_signature`, `challenge_not_yet_valid`, `challenge_expired`,
`challenge_already_consumed`, `challenge_mismatch`, `origin_mismatch`,
`cross_origin_disallowed`, `rp_id_hash_mismatch`.

Still write a rejected result and mark the job processed when the batch commits.

### Authenticated policy failures (consume challenge)

Once credential/user are active, client/authenticator data are structurally valid,
signature verifies, challenge is current/unused/bound, origin allowed, crossOrigin
absent/false, and RP ID hash matches, the assertion is authenticated and ceremony-bound.

Then the challenge is consumed even if later rejected for:
`user_presence_required`, `user_verification_required`, `backup_flags_invalid`,
`backup_eligibility_changed`, `signature_counter_replay`.

For UP/UV/backup-flag/backup-eligibility rejection: consume challenge; rejected result; do not otherwise mutate credential.

For strict signature-counter replay: consume challenge; rejected result; set `credential.status = quarantined`; do not change `sign_count`, `backup_state`, or `last_used_at`.

## Signature-counter policy

Let `stored = credentials.sign_count`, `received = authenticatorData.signCount`.

Truth table:

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

* **Unsupported** (`stored = 0` and `received = 0`): accept if other rules pass; leave stored `0`; risk null.
* **Advance** (`received > stored`): accept; set stored to `received`; risk null.
* **Non-increasing nonzero** (`(stored != 0 or received != 0)` and `received <= stored`):
  * If `backup_eligible = 0` **or** policy is `strict`: reject `signature_counter_replay`; consume; quarantine; leave count unchanged.
  * If `backup_eligible = 1` **and** policy is `backup_aware`: accept with risk `non_monotonic_backup_counter`; stored becomes `max(stored, received)` (never decreases); do not quarantine.

## Per-assertion state snapshots

Eligible assertions are processed sequentially in the published chronological
order inside one transaction.
`sign_count_before_or_null` is the stored credential `sign_count` immediately before
the current assertion, including mutations committed by earlier eligible
assertions in the same batch.
`sign_count_after_or_null` is the stored credential `sign_count` immediately after
applying the current assertion's documented mutation boundary.
These fields are not snapshots of the original fixture row.

## Backup eligibility and state

For authenticated ceremony-bound assertions:

* incoming BE must equal stored `backup_eligible`
* incoming BS requires incoming BE
* stored BE never changes

On **accepted** assertions: `backup_state = incoming BS`, `last_used_at = assertion.received_at`.
On rejected assertions: do not change `backup_state` or `last_used_at`.
Backup-aware accepted counter-risk cases are accepted and may update `backup_state` and `last_used_at`.

## Challenge lifecycle

Valid when:

* `challenge.rp_id = credential.rp_id`
* `received_at >= issued_at`
* `received_at <= expires_at` (inclusive expiration)
* consumed fields null
* clientDataJSON challenge matches challenge bytes

When consumed: `consumed_at = assertion.received_at`, `consumed_by_assertion_id = assertion.assertion_id`.
Never consume for a future ignored job.

## Batch transaction

Use one explicit write transaction for the eligible batch (`BEGIN IMMEDIATE` semantics).

Within the transaction: process every eligible job in order; write exactly one result per eligible job; mark jobs processed; apply challenge/credential changes; derive the report from transaction state.

On unexpected database/serialization/invariant error: roll back entire batch; leave eligible jobs pending; no new results; credentials/challenges unchanged; remove outputs; nonzero exit; nonempty stderr.

Request-level rejection is not a transaction failure. Batches with rejected assertions still commit when processing succeeds.
