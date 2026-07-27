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
