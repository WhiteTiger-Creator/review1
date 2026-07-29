The credential-store service under `/app` must correctly recover interrupted online generation rotations. Repair the Rust implementation under `/app/m03/src/` so active reader snapshots, publication isolation, cleanup safety, nonce reservation accounting, and legacy import compatibility remain correct. Malformed recovery must fail atomically without mutating durable state. This is a source-fix task: rebuild `/app/m03` from source and exercise the repaired binaries through the documented CLI and HTTP contract. Static or manual database edits are insufficient because validation rebuilds the service and reruns the behavioral verifier pipeline.

Detailed behavior is defined in `/app/OPERATIONS.md`, `/app/docs/generation-handoff.md`, `/app/docs/database-compatibility.md`, and `/app/docs/api-contract.md`. Existing CLI and HTTP response structures must remain compatible with those documents. The HTTP daemon binds to loopback (default `127.0.0.1:9470`) and accepts `--listen <host:port>` for alternate bind addresses.

Rebuild and use the service binaries at `/app/bin/opsctl` and `/app/bin/opsd`.

## Required behavior

1. **Generation-local nonce uniqueness** — Within each generation, no two committed ciphertext rows may share the same `(key_id, nonce)` pair. This applies to every commit path: ordinary `put` writes, rotation copies, and legacy import. Matching nonce values across different generations are allowed. Enforce this in application logic (commit and validation paths), not with SQLite `UNIQUE` indexes on `(key_id, nonce)` or `(generation_id, key_id, nonce)`. Recovery must be able to inspect existing committed rows and reject duplicate pairs already present in corrupt state.

2. **Ordinary writes** — Each new committed row in a generation must receive a distinct nonce allocation slot. First-time writes to different `record_id` values must not collide merely because each record's version counter starts at `(epoch, counter) = (0, 1)`.

3. **Published read isolation** — `opsctl get` and unpinned HTTP reads consult only the published generation. If a record is absent there, the read fails as not found even when older generations still contain that `record_id`.

4. **Rotation copy** — Copying decrypts each source occurrence and re-encrypts it under the target generation's active key with a reserved target-generation nonce. Interrupted copies resume from the durable reservation ledger, reconcile a lagging cursor without re-copying committed target rows, roll reservation batches forward monotonically, and never reuse committed `(key_id, nonce)` pairs or consumed reservations. A final short batch may leave unused reservation capacity. Each occurrence is copied in its own durable transaction. With `KSEAL_FAILPOINT=after-partial-copy`, both `opsctl upgrade` and `opsctl recover` exit with code **75** immediately after committing one copied occurrence, advancing `copy_cursor` before exit; repeated `opsctl recover` invocations must converge. Do not wrap an entire recovery copy loop in one outer transaction that prevents these mid-loop crash barriers from firing.

5. **Validate-then-publish** — Target validation (canonical occurrence parity, reservation accounting, generation-local nonce uniqueness) completes before a generation becomes published. Failed validation during recovery returns a nonzero exit code and leaves the database file and audit log unchanged. Reservations consumed by a completed earlier rotation must not fund rows in a later rotation's target generation.

6. **Legacy import** — Import into a fresh database or an initialized-but-empty current-schema target (schema version 3, generation 1 present, zero credential rows, no active upgrade) must succeed atomically without unique-constraint failures. Unsupported sources and non-empty targets fail without mutation. When multiple source rows share a `record_id`, the winner is the lexicographically greatest `(version_epoch, version_counter)` — epoch first, then counter; counter-only comparison is incorrect. Schema version 1 sources store rows in `legacy_records`; schema version 2 sources use `records`.

7. **Reader pins and cleanup** — Pinned readers keep their generation across daemon restart, recovery, and cleanup. Cleanup retains every generation still referenced by an active reader pin or an unfinished upgrade journal.

`opsctl status --json` and `GET /v1/status` expose `database_path`, `schema_version`, `current_generation`, `published_generation`, `upgrade_phase`, `upgrade_id`, `active_reader_count`, and `generation_states`.

See `/app/docs/generation-handoff.md` for crash barriers, cursor semantics, reservation-ledger provenance, and successive-rotation rules.
