# Generation handoff and recovery

The credential store service supports online generation rotations while API readers retain pinned snapshots of older database generations.

## Rotation phases

A rotation progresses through durable phases recorded in `upgrade_journal` and `generation_catalog`:

1. **reserved** — nonce batch reserved for target generation copy
2. **copying** — records copied from source to target generation in configurable batches
3. **copied** — all source records copied to target
4. **validated** — target generation validated (record counts, nonce reservations)
5. **published** — target generation published as current for new readers
6. **pins_reconciled** — durable reader pins reconciled to reference correct generations
7. **cleanup_pending** — obsolete generations eligible for cleanup
8. **complete** — rotation finished

Publication is **not** the terminal commit point. A rotation is complete only after pin reconciliation and cleanup eligibility are recorded. A target generation must be validated before it becomes visible as published. Failed validation must leave the prior published generation authoritative.

## Crash barriers

Set `KSEAL_FAILPOINT` to one of the following documented barrier names to simulate a process exit immediately after the corresponding durable commit. The process exits with code **75**.

| Barrier name | Durable state after exit |
|---|---|
| `after-reservation` | Nonce reservation batch committed |
| `after-partial-copy` | Some target rows committed, cursor may not advance |
| `after-copy-complete` | All rows copied, cursor at end |
| `after-target-validation` | Target validated in catalog |
| `after-publication` | Target published, pins not yet reconciled |
| `after-pin-reconciliation` | Pins reconciled, cleanup not run |
| `during-cleanup` | Cleanup in progress |

Recovery must converge every interrupted rotation to the same logical database contents as an uninterrupted rotation.

## Copy identity and cursor semantics

The source generation is copied in this canonical order:

```text
record_id ascending
version_epoch ascending
version_counter ascending
```

Each source occurrence is identified by:

```text
(record_id, version_epoch, version_counter)
```

The durable `copy_cursor` identifies the next occurrence in that canonical sequence whose completion must be reconciled.

1. A committed target occurrence may exist even when `copy_cursor` still points at it because the row transaction and cursor transaction may be separated by a crash barrier.
2. On recovery, if the target already contains the corresponding committed occurrence, recovery must verify that the occurrence is compatible with the active upgrade, preserve its existing target ciphertext, key ID, and nonce, preserve its consumed reservation, advance the cursor, avoid allocating another reservation, and avoid re-encrypting the row.
3. Recovery must not identify copied work using `record_id` alone when multiple versions exist.
4. A cursor that is behind committed work is recoverable.
5. A cursor that skips a required source occurrence without a compatible committed target occurrence is malformed state.
6. Copy completion means every canonical source occurrence has one compatible target occurrence. It is not merely equality of distinct record-ID counts.

## Repeated recovery across batches

The same upgrade may be interrupted and resumed repeatedly. For example, an execution may copy one occurrence, crash, recover and copy another occurrence, crash, cross a reservation-batch boundary, crash, and recover to completion. The final state must equal an uninterrupted upgrade in logical records, record versions, target generation, reader behavior, committed nonce uniqueness, reservation accounting, publication state, and cleanup eligibility. The number and placement of prior resumptions must not affect the converged result.

## Reader snapshot guarantees

- Durable reader tokens remain valid across daemon restart and recovery.
- Existing pinned readers observe the generation they originally pinned until explicitly released.
- New readers observe only the published generation.
- Ordinary current reads never fall back to older generations for a record missing from the published generation.

## Nonce uniqueness

Within a single generation, committed ciphertext rows must not share the same `(key_id, nonce)` pair. Uniqueness is generation-local: source and target generations may legitimately contain matching nonce values (for example before re-encryption during copy). Do not enforce a global cross-generation unique constraint on `(key_id, nonce)`.

When copying, each target row must be decrypted with the source key/nonce and re-encrypted under the active target key with a freshly reserved target-generation nonce. Resuming an interrupted copy must not consume another reservation for a destination row that is already present; advance the durable cursor instead. Exhausted reservation batches require additional batches rather than restarting slot numbering in a way that reuses a committed target `(key_id, nonce)`.

Reservation batches are numbered monotonically within one `upgrade_id`. Slots are numbered from `0` through `batch_size - 1` inside each batch. The reservation identity is:

```text
(upgrade_id, batch_number, slot)
```

The cryptographic allocation identity includes the target generation and reservation coordinates. Exhausting a batch requires creating or reusing the next numbered batch. Slot numbering may restart at zero only because the batch number changes. Recovery must never return to an exhausted earlier batch and reuse one of its consumed slots. Batch rollover may occur multiple times during one upgrade. Correctness must hold when `record_count > batch_size`, `record_count > 2 * batch_size`, `record_count` is not divisible by `batch_size`, and `batch_size = 1`. A final short batch may contain unused reservations and remains valid.

### Committed-row reservation accounting

For the active target generation:

1. Every newly copied committed target occurrence corresponds to exactly one consumed reservation from the active upgrade.
2. That reservation has the same `key_id`, `nonce`, and `record_id` as the committed target occurrence it funded.
3. A consumed reservation cannot fund two target rows.
4. A target row cannot be funded by two consumed reservations.
5. A consumed reservation cannot remain orphaned after successful completion.
6. An unconsumed reservation must not name a committed record.
7. Unused unconsumed capacity in the final batch is valid and may either remain unused or be retired.
8. Validation concerns committed rows and consumed reservations, not the requirement that every reserved slot be consumed.
9. Matching nonce text in different generations is not, by itself, invalid.
10. Matching `(key_id, nonce)` values among two committed rows in the same generation are invalid.

The contract allows more than one correct internal reservation strategy.

Nonce reservations represent available allocation capacity, not a requirement that every reserved slot become consumed. A reservation batch may contain more slots than the number of records remaining to copy. After all source records have been copied, unused slots are valid and may be retired or removed without making the target invalid.

A reservation is consumed only when its `(key_id, nonce)` is bound to a successfully committed target-generation ciphertext row. A committed target row must correspond to no more than one consumed reservation. A consumed reservation must never be reused for another target row. During resumed copying, an already committed destination row must not consume another reservation. Unused reservations may remain available while copying is incomplete. Once copying is complete, unused reservations may be discarded or marked retired.

Target validation must not fail solely because unused reservation capacity exists. Target validation must reject duplicate committed `(key_id, nonce)` pairs within the target generation. Nonce uniqueness remains scoped to committed rows within one generation. Matching nonce values in different generations are not, by themselves, invalid. Legacy imports must not be rejected merely because separate source records or generations contain matching nonce values.

With `batch_size = 3` and one record left to copy, consuming one reservation and leaving two unused reservations is valid. The unused slots do not represent missing records or duplicate committed nonces.

## Validation boundary

A target may be published only after all of the following have been validated:

- every canonical source occurrence exists compatibly in the target
- no unexpected target occurrence replaces or hides required source state
- committed `(key_id, nonce)` values are unique within the target generation
- committed rows and consumed reservations satisfy the one-to-one accounting contract
- the journal source and target generations exist
- the target belongs to the active upgrade
- required copied rows decrypt successfully under their recorded target key and nonce
- the target has not already been contradicted by malformed reservation state

If validation fails:

- the previously published generation remains authoritative
- the target must not become published
- the journal, catalog, records, reservations, database bytes, WAL/SHM state, and audit log remain unchanged from the state immediately before recovery was invoked

## Successive rotations

A successfully published target may later become the source of another rotation. Each rotation has its own upgrade ID, target generation, reservation batches, cursor, and journal history. Nonce uniqueness is enforced independently within every generation. Writes committed to the currently published generation between rotations must be copied by the next rotation. A reader pinned before the first rotation remains on its original generation. A reader opened after the first publication but before the second publication remains on the intermediate generation. Newly opened readers after the second publication use only the newest published generation. Cleanup must retain every generation still required by any active reader or unfinished journal. Closing one reader must not release another reader's generation. Repeating cleanup and recovery must remain idempotent across successive rotations.

## Idempotency

Running `opsctl recover` multiple times on the same database must be idempotent. Failed recovery on malformed state must not modify the database or audit log. Cleanup must likewise be idempotent once converged, and must retain any generation that is published, pinned, the newest catalog generation, or referenced as source or target by an unfinished upgrade journal.

## CLI commands

All commands accept `--db <path>` to operate on an arbitrary database file.

```text
opsctl init
opsctl put <record_id> <payload>
opsctl get <record_id>
opsctl reader-open
opsctl reader-get <token> <record_id>
opsctl reader-close <token>
opsctl upgrade
opsctl recover
opsctl cleanup
opsctl status
opsctl inspect
opsctl import-legacy --source <path>
opsctl reset-demo
```

`import-legacy` accepts `--source` with the path to a supported legacy SQLite database. See `/app/docs/database-compatibility.md` for fresh-target, empty-initialized-target, version ordering, and non-empty rejection rules.

Use `--json` for structured output on supported commands.
