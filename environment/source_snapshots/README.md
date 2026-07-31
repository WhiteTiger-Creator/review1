# Source snapshots (conceptual grounding)

Retrieval date: **2026-07-19**.

This task implements a **bounded WebAuthn authentication-assertion audit profile**.
It does not reproduce every WebAuthn Level 3 or SQLite implementation detail.

## Primary sources

| Source | URL | Sections used |
| --- | --- | --- |
| WebAuthn Level 3 | https://www.w3.org/TR/webauthn-3/ | §6.1 Authenticator Data; §7.2 Verifying an Authentication Assertion (client data, RP ID hash, UP/UV, signature over `authenticatorData \|\| SHA-256(clientDataJSON)`, signature counter); credential backup flags (BE/BS); ES256 / COSE alg -7 |
| SQLite transactions | https://www.sqlite.org/lang_transaction.html | `BEGIN IMMEDIATE` acquires a reserved write lock before later reads can be invalidated by another writer |
| SQLite isolation | https://www.sqlite.org/isolation.html | Writer serialization; WAL readers observe snapshot isolation (not reproduced as a concurrency race in this task) |
| SQLite result codes | https://www.sqlite.org/rescode.html | Failure classification for unexpected database errors |
| SQLite WAL | https://www.sqlite.org/wal.html | WAL overview; this task does not require candidates to reproduce concurrent reader/writer races |

## Concise citations

* WebAuthn verifies assertion signatures over the binary concatenation of
  authenticator data and the SHA-256 hash of the **original** `clientDataJSON`
  bytes (not a reserialized object).
* ES256 assertion signatures use ASN.1 DER `Ecdsa-Sig-Value` encoding.
* A non-increasing nonzero signature counter is a **signal**, not proof, that an
  authenticator may be cloned. Relying-party response is a published policy in
  this bounded profile (`strict` vs `backup_aware`).
* The BE flag is a permanent credential property; BS may be set only when BE is set.
* SQLite serializes writers; `BEGIN IMMEDIATE` starts a write transaction before
  dependent reads proceed inside that transaction.

Do not copy entire official webpages into this repository.
