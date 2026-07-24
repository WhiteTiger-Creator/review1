# Artifact retention operations

The retention stack under `/app` serves `/var/lib/mint` with offline vendored Cargo builds. Rebuild after changes:

```bash
cargo build --release --workspace --locked --offline --manifest-path /app/Cargo.toml
```

## Commands

```bash
cargo run --release -p m07 -- inspect --root /var/lib/mint
cargo run --release -p m07 -- recover --root /var/lib/mint --output /output/store-inventory.json
cargo run --release -p m07 -- run-image --root /var/lib/mint --image <name> --result /output/run-result.json
cargo run --release -p m07 -- gc --root /var/lib/mint
cargo run --release -p m07 -- import --root /var/lib/mint --bundle /app/fixtures/base-store/demo-bundle.json
cargo run --release -p m07 -- verify-store --root /var/lib/mint
```

Helper scripts live in `/app/scripts/`. Case fixtures are under `/app/cases/`.

Configuration: `/app/config/daemon.toml`, `gc.toml`, `recovery.toml`.

See `/app/docs/inventory-contract.md` for inventory output schema.

Grading runs `python -m pytest --ctrf /logs/verifier/ctrf.json` against the documented CLI workflows.

Preflight layout check: `bash -lc 'cd /app/environment 2>/dev/null || cd /app && test -f Cargo.toml'`
