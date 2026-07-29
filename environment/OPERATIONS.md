# Credential store service operations

All builds and workflows run from `/app` (also linked as `/app/environment`) with locked offline dependencies.

## Build

```bash
cd /app
cargo build --release --locked --offline
cp target/release/opsctl /app/bin/opsctl
cp target/release/opsd /app/bin/opsd
```

The login shell resolves `cargo`, `rustc`, `opsctl`, and `opsd` from `/usr/local/bin`.

## Initialize state

```bash
opsctl init --db /app/state/store.db
```

## Run daemon

```bash
KSEAL_CONFIG=/app/config/service.toml \
KSEAL_DB=/app/state/store.db \
KSEAL_AUDIT=/app/state/store.audit.jsonl \
/app/bin/opsd
```

## Inspect generation state

```bash
opsctl status --json --db /app/state/store.db
opsctl inspect --json --db /app/state/store.db
```

Status JSON includes `database_path`, `schema_version`, `current_generation`, `published_generation`, `upgrade_phase`, `upgrade_id`, `active_reader_count`, and `generation_states`.

## Generation rotation workflow

```bash
opsctl upgrade --db /app/state/store.db
opsctl recover --db /app/state/store.db
opsctl cleanup --db /app/state/store.db
```

Crash barriers for interrupted rotations are documented in `/app/docs/generation-handoff.md`.

## Legacy import

```bash
opsctl import-legacy --source /path/to/legacy.db --db /app/state/store.db
```

See `/app/docs/database-compatibility.md` for supported versions and target policies.

## Repair scope and observable symptoms

Most defects live in the generation rotation, copy/reservation, compatibility read, legacy import, and recovery modules under `/app/m03/src/`.

Common symptoms that indicate incorrect behavior:

| Symptom | Likely contract area |
|---|---|
| Multiple distinct `opsctl put` records in the same generation share a `(key_id, nonce)` pair | Ordinary write nonce allocation (`database-compatibility.md`) |
| `opsctl get` returns a record that exists only in an older generation | Published read isolation (`database-compatibility.md`) |
| Partial-copy recovery reuses a committed target `(key_id, nonce)` or fails after exhausting a reservation batch | Copy identity and batch continuation (`generation-handoff.md`) |
| `opsctl recover` with `KSEAL_FAILPOINT=after-partial-copy` completes in one invocation instead of exiting 75 after each copied occurrence | Recovery failpoint semantics (`generation-handoff.md`) |
| Recovery publishes a target before validation completes, or mutates the database when validation should fail | Validation boundary (`generation-handoff.md`) |
| Corruption-injection tests fail at setup with `IntegrityError` on nonce insert | Application-level uniqueness enforcement (`database-compatibility.md`) |
| `import-legacy` fails with `generation_catalog` unique constraint on an initialized-empty target | Legacy import target policy (`database-compatibility.md`) |
| Legacy import picks the wrong version when source row order differs from canonical `(epoch, counter)` order | Record version semantics (`database-compatibility.md`) |
| Legacy v1 import reads from `records` instead of `legacy_records` | Legacy source table names (`database-compatibility.md`) |

Rebuild after source changes and verify with `opsctl status --json`, `opsctl inspect --json`, and the documented crash barriers in `/app/docs/generation-handoff.md`.
