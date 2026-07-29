# Data contract

## Inputs

| File | Role |
|---|---|
| `/app/data/audit_requests.ndjson` | Per-request audit jobs |
| `/app/data/environment_overrides.json` | Named environment profiles |
| `/app/data/cli_overrides.ndjson` | Ordered CLI `--config` profiles |
| `/app/data/source_profiles.json` | Expected source package identities |
| `/app/data/solver_config.json` | Explicit numeric limits |

## audit_requests.ndjson fields

`request_id`, `invocation_directory`, `environment_profile_id`, `cli_override_profile_id`, `workspace_manifest`, `existing_lock`, `run_build`, `output_report_name`

Paths are fixture-root relative. Physical NDJSON order is not semantic.

## Precedence stack (high level)

```text
ancestor configs → includes → deeper configs → environment → CLI --config (LTR)
```

See sibling contracts for discovery, include, merge, path, and source-replacement rules.

## Fixture root

Runtime fixture root:

```text
/app/fixture-tree/config-root
```

`--fixture-root` must name an **existing directory**. A missing path, a regular
file, or any non-directory path is a **whole-run fatal error** (nonzero exit,
nonempty stderr, no successful final report; remove any stale final output and
temporary sibling before exiting). Do not treat an invalid fixture root as an
accepted request with empty rows.