# Report schema

Emit one JSON object to the configured output path. Machine-readable companion:
`/app/docs/report.schema.json` (JSON Schema draft-07). The Markdown and JSON Schema
must not disagree; both are normative.

## Top-level keys (exact field order)

```text
request_rows
discovered_config_rows
include_rows
effective_value_rows
path_resolution_rows
source_rows
replacement_edge_rows
package_source_rows
lock_reconciliation_rows
integrity_rows
build_rows
rejection_rows
summary
```

Do not sort top-level keys alphabetically. Row object field order is exactly the
order listed under each row type below.

## Bounded vocabulary

### `merge_layer`

Exact values only:

- `config_file`
- `environment`
- `cli`

### `value_type`

- `string`
- `integer`
- `boolean`
- `array`
- `table`

### `source_kind`

- `replace`
- `directory`
- `local-registry`

### Request `status`

- `accepted`
- `rejected`

### Request `build_status`

- `success`
- `failed`
- `skipped`
- `not_run`

### Build row `status`

- `success`
- `failed`

### Lock reconciliation `status`

- `matched`
- `package_missing`
- `checksum_mismatch`
- `source_mismatch`

### `integrity_kind`

Exact bounded vocabulary (no aliases):

- `directory_identity`
- `directory_checksum`
- `directory_file`
- `directory_symlink`
- `directory_unexpected_file`
- `local_registry_index`
- `local_registry_archive`
- `local_registry_identity`
- `local_registry_path`

### Integrity `status` (by kind)

#### `directory_identity`

- Success: `status = "ok"`, `details = "manifest matches"`
- Missing package directory: `status = "package_missing"`
- Manifest name/version mismatch: `status = "identity_mismatch"`,
  `details = "<observed-name>@<observed-version>"`

#### `directory_checksum`

- Success: `status = "ok"`, `details` = package checksum
- Disagreement: `status = "checksum_mismatch"`

#### `directory_file`

For each checksum-listed regular file:

- Success: `status = "ok"`, `details` = package-relative file path
- Missing: `status = "missing_file"`
- Content mismatch: `status = "checksum_mismatch"`

#### `directory_symlink`

Emit when an unsafe package symlink is found: `status = "unsafe_symlink"`

#### `directory_unexpected_file`

Emit when a package regular file other than `.cargo-checksum.json` is absent
from the checksum file: `status = "unexpected_file"`

#### `local_registry_index`

- Success: `status = "ok"`, `details` = index checksum
- Missing index/package version: `status = "package_missing"`

#### `local_registry_archive`

- Success: `status = "ok"`, `details` = archive SHA-256
- Missing archive: `status = "package_missing"`
- Archive/index/lock disagreement: `status = "checksum_mismatch"`

#### `local_registry_identity`

- Success: `status = "ok"`, `details = "manifest matches"`
- Missing/mismatching archive Cargo.toml: `status = "identity_mismatch"`

#### `local_registry_path`

- After all archive paths are safe: `status = "ok"`,
  `details = "safe archive paths"`
- Unsafe path: `status = "unsafe_path"`

### Rejection stages (emitted)

`discovery`, `include`, `environment`, `path`, `source`, `integrity`, `lock`,
`build`

### Rejection reasons (emitted)

`invocation_directory_missing`, `path_escape`, `include_cycle`,
`required_include_missing`, `maximum_include_depth_exceeded`,
`maximum_include_count_exceeded`, `unknown_environment_profile`,
`replacement_cycle`, `missing_replacement_target`, `ambiguous_terminal_source`,
`package_missing`, `checksum_mismatch`, `identity_mismatch`, `unsafe_symlink`,
`unexpected_file`, `missing_file`, `unsafe_path`, `source_mismatch`,
`missing_terminal_source`, `locked_offline_build_failed`

## Row fields

### `request_rows`

Field order: `request_id`, `invocation_directory`, `status`, `reason_or_null`,
`discovered_config_count`, `include_count`, `effective_value_count`,
`terminal_source_count`, `build_status`

Sort key: `request_id`

Population: one row per audit request.

When `run_build = false`, `build_status = "skipped"`. When a request is rejected
before build, `build_status = "not_run"`.

### `discovered_config_rows`

Field order: `request_id`, `config_path`, `discovery_depth`, `load_order`

Sort key: `request_id`, `load_order`, `config_path`

- `config_path` is fixture-root-relative with `/` separators.
- `discovery_depth = 0` at the invocation directory; depth increments by one
  toward the fixture root.
- Rows are loaded shallow-to-deep (fixture-root-near first, invocation-near last).
- `load_order` is **1-based** within discovered configs for the request.
  The first loaded (shallowest) file has `load_order = 1`, the next `2`, and so on.
  Do not use zero-based indexing.

### `include_rows`

Field order: `request_id`, `including_file`, `included_path`, `optional`,
`exists`, `include_depth`, `load_order`

Sort key: `request_id`, `load_order`, `included_path`

`include_rows.load_order` is a **separate** per-request include-event clock
(not shared with discovered-config `load_order`). An include event receives a
positive integer when encountered; values increase strictly in processing order:

1. Process top-level discovered configs shallow-to-deep.
2. Within each file, process `include` declarations left-to-right.
3. Record the include row **before** recursively loading that include.
4. Recurse depth-first.
5. After all includes for a file, merge the including file’s own keys.
6. A missing optional include still consumes an encounter position.

Trusted implementations use consecutive integers starting at `1`.

### `effective_value_rows`

Field order: `request_id`, `key`, `value_type`, `canonical_value`,
`defining_source`, `merge_layer`, `environment_override_or_null`,
`cli_override_sequence_or_null`

Sort key: `request_id`, `key`

Bounded keys only: `build.jobs`, `build.incremental`, `build.rustflags`,
`build.target-dir`, `net.offline`, `term.quiet`, `term.verbose`, `term.color`,
and `source.<name>.{replace-with,directory,local-registry}`.

#### `canonical_value` encoding

| `value_type` | Encoding |
|---|---|
| `string` | Raw string content (no surrounding JSON quotes) |
| `integer` | Base-10 integer string (example: `"8"`) |
| `boolean` | `"true"` or `"false"` |
| `array` | Compact JSON array, no unnecessary whitespace (example: `["-C","opt-level=2"]`) |
| `table` | Compact JSON object with keys in deterministic lexical order |

Do not use TOML debug/display syntax for arrays or tables.

#### `defining_source` and `merge_layer` provenance

| Origin | `merge_layer` | `defining_source` | env / cli nullability |
|---|---|---|---|
| Hierarchical or included config | `config_file` | Fixture-root-relative defining TOML path | both null |
| Environment | `environment` | Exact string `environment` | `environment_override_or_null` = env var name; CLI null |
| CLI inline | `cli` | `cli:<sequence>` | `cli_override_sequence_or_null` = sequence; env null |
| CLI file | `cli` | Fixture-root-relative CLI TOML path | `cli_override_sequence_or_null` = sequence; env null |

Example: environment override `CARGO_TERM_VERBOSE` must emit
`merge_layer = "environment"`, `defining_source = "environment"`,
`environment_override_or_null = "CARGO_TERM_VERBOSE"`,
`cli_override_sequence_or_null = null`.
Do **not** put `environment:CARGO_TERM_VERBOSE` in `defining_source`.

### `path_resolution_rows`

Field order: `request_id`, `key`, `raw_path`, `base_path`, `normalized_path`,
`exists`

Sort key: `request_id`, `key`

Path bases follow `/app/docs/path_contract.md`.

### `source_rows`

Field order: `request_id`, `source_name`, `source_kind`, `replace_with_or_null`,
`terminal_source`, `root_path_or_null`

Sort key: `request_id`, `source_name`

Population: one row for every effective source name.

`terminal_source` is a **string**: the terminal source **name** reached after
following `replace-with` edges. For a terminal source itself,
`terminal_source = source_name`. It is not a Boolean.

| Kind | Fields |
|---|---|
| `replace` | `replace_with_or_null` = next source; `root_path_or_null` = null; `terminal_source` = final terminal name |
| `directory` | `replace_with_or_null` = null; `root_path_or_null` = normalized terminal root; `terminal_source` = `source_name` |
| `local-registry` | `replace_with_or_null` = null; `root_path_or_null` = normalized terminal root; `terminal_source` = `source_name` |

Example chain `crates-io → vendor-bridge → vendor-primary`:

- `crates-io.terminal_source = "vendor-primary"`
- `vendor-bridge.terminal_source = "vendor-primary"`
- `vendor-primary.terminal_source = "vendor-primary"`

### `replacement_edge_rows`

Field order: `request_id`, `from_source`, `to_source`, `edge_index`

Sort key: `request_id`, `from_source`, `edge_index`, `to_source`

Each traversed replacement edge emits one row. `edge_index` is **1-based**
within the explored replacement chain for that origin.

Example `crates-io → vendor-bridge → vendor-primary`:

- `crates-io → vendor-bridge` has `edge_index = 1`
- `vendor-bridge → vendor-primary` has `edge_index = 2`

Do not emit zero-based indices.

### `package_source_rows`

Field order: `request_id`, `package_name`, `version`, `original_source`,
`terminal_source`, `relative_package_path`

Sort key: `request_id`, `package_name`, `version`

After successful terminal-source resolution, parse registry packages from
`Cargo.lock`. Emit one row per registry package.

- Directory: `<terminal-root>/<package-name>-<version>`
- Local-registry: `<terminal-root>/<package-name>-<version>.crate`

Workspace packages without registry provenance do not create these rows.

### `lock_reconciliation_rows`

Field order: `request_id`, `package_name`, `version`, `lock_source`,
`effective_source`, `checksum`, `status`

Sort key: `request_id`, `package_name`, `version`

Emit **one row for every registry package** that reaches lock reconciliation.
Successful packages are **not** omitted. A valid package must emit
`status = "matched"`.

`effective_source` format: `"<source-kind>:<terminal-root>"`

Examples:

- `directory:project/workspace/vendor-primary`
- `local-registry:project/workspace/local-registry`

### `integrity_rows`

Field order: `request_id`, `source_name`, `package_name`, `version`,
`integrity_kind`, `status`, `details`

Sort key: `request_id`, `package_name`, `version`, `integrity_kind`, `details`

Populate according to the integrity vocabulary above for each verified package.

### `build_rows`

Field order: `request_id`, `status`, `exit_code`, `lock_unchanged`,
`source_bytes_unchanged`, `artifact_count`

Sort key: `request_id`

- When `run_build = false`: emit **no** build row; request `build_status = "skipped"`.
- When `run_build = true` and the request is accepted through build: emit exactly
  one build row.

Build command:

```text
cargo build --release --locked --offline --manifest-path <copied workspace Cargo.toml> -p cli
```

Successful canonical build:

- `status = "success"`
- `exit_code = 0`
- `lock_unchanged = true`
- `source_bytes_unchanged = true`
- `artifact_count = 1`

A build is successful only when Cargo exits 0, `Cargo.lock` bytes remain
unchanged, terminal source bytes remain unchanged, and the final `cli`
executable exists. `artifact_count = 1` counts that final `cli` executable only.
Do not count rlibs, rmeta files, build scripts, dependency artifacts,
fingerprints, incremental files, or every `target/release` entry.

### `rejection_rows`

Field order: `request_id`, `stage`, `reason`, `path_or_source_or_null`, `details`

Sort key: `request_id`, `stage`, `reason`

### `summary`

Field order: `request_count`, `accepted_request_count`, `rejected_request_count`,
`discovered_config_count`, `include_count`, `effective_source_count`,
`verified_package_count`, `successful_build_count`, `failed_build_count`

## Ordering

Use ordinary Unicode/UTF-8 lexical string ordering consistently. Exact sort keys
are listed with each row type above.

## JSON serialization

- UTF-8
- Two-space JSON indentation (`serde_json` pretty / equivalent)
- Exactly one trailing LF
- Top-level field order exactly as listed
- Row object field order exactly as documented (do not alphabetically sort keys
  unless the schema lists them in that order)

## Output atomicity and temporary sibling

Final output path: `<output-path>`

Temporary sibling: `<output-path>.tmp`

Examples:

- `audit_report.json` → temporary `audit_report.json.tmp`
- `custom.json` → temporary `custom.json.tmp`

Before work:

1. Remove stale final output if present.
2. Remove stale exact temporary sibling if present.

On success:

1. Write the complete JSON to the temporary file.
2. Flush and close.
3. Atomically rename temporary → final.
4. Temporary file must be absent afterward.

## Whole-run fatal errors

Whole-run fatal errors require:

- Nonzero process exit
- Nonempty stderr
- No successful report
- No partial successful report
- Final output absent
- Temporary sibling absent

Examples of whole-run fatal conditions:

- `--fixture-root` is missing, is a regular file, or is otherwise not a directory
- Required CLI input files cannot be read
- Report serialization/write failure after validation

Do not encode a whole-run fatal structural error as exit 0 with a request-level
`rejected` status unless the public contract classifies that condition as a
request-level rejection.
