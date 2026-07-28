Effective Cargo configuration for an offline workspace is wrong when hierarchical
`.cargo/config.toml` discovery, recursive includes, environment overrides,
left-to-right `--config` flags, config-relative paths, and `[source]`
replacement chains disagree with the locked package provenance those settings
are supposed to feed.

Rebuild the Rust auditor at `/app/auditor` so it reconstructs the effective
configuration for each audit request under `/app/fixture-tree/config-root`,
validates directory and local-registry terminal sources against `Cargo.lock`,
optionally performs a locked offline build from the resolved terminal sources,
and writes one deterministic JSON report.

## Deliverable

```bash
cargo build \
  --release \
  --locked \
  --offline \
  --manifest-path /app/auditor/Cargo.toml
```

Required executable:

`/app/auditor/target/release/cargo-config-source-replacement-precedence-auditor`

Run:

```bash
/app/auditor/target/release/cargo-config-source-replacement-precedence-auditor \
  --fixture-root /app/fixture-tree/config-root \
  --requests /app/data/audit_requests.ndjson \
  --environment-overrides /app/data/environment_overrides.json \
  --cli-overrides /app/data/cli_overrides.ndjson \
  --source-profiles /app/data/source_profiles.json \
  --solver-config /app/data/solver_config.json \
  --output /app/output/audit_report.json
```

The verifier rebuilds the candidate with a clean locked offline Cargo release
build and executes that native binary directly.

Do not replace the auditor with Python/shell wrappers, precomputed reports,
copied Oracle/reference code, or `cargo config` / network registry queries.
Modify only `/app/auditor`. Fixture tree, data files, and docs are immutable.

## Scope

Bounded contracts live under `/app/docs/`:

- `/app/docs/data_contract.md`
- `/app/docs/discovery_contract.md`
- `/app/docs/include_contract.md`
- `/app/docs/merge_contract.md`
- `/app/docs/path_contract.md`
- `/app/docs/source_replacement_contract.md`
- `/app/docs/report_schema.md`
- `/app/docs/report.schema.json`

The exact report row schemas, enum values, index bases, canonical value
encoding, provenance strings, row populations, sorting, integrity vocabulary,
JSON serialization, temporary sibling path, and whole-run fatal exit behavior
are normative in `/app/docs/report_schema.md` and `/app/docs/report.schema.json`.

Frozen Cargo Book excerpts are in the task `SOURCES.md` / `source_snapshots/`
tree for authoring provenance; runtime stays offline.
