Our CMake superbuild lost its configure environment, but the bounded evidence
under `/app/data` is still here: FetchContent declarations, find_package
requests, provider responses, source-dir overrides, package-config candidates,
target dependency metadata, prior resolution-lock sections, and four configure
requests. We need a native reconciler that reconstructs which source would
satisfy each request and whether prior lock sections can be reused.

Finish the unfinished reconciler in `/app`. Binary name is `cmake-reconciler`.
Keep the existing `reconcile` entrypoint. Canonical invocation reads `/app/data`
(or another `--data-dir`) and writes `/app/output/resolution_report.json` (or
`--report-out`). This is a bounded CMake-inspired dependency-provider and
FetchContent reconciliation profile — not full CMake compatibility. Do not run
CMake, download anything, or substitute Python/shell dumps for the native
binary. The crate is vendored for offline Cargo builds.

Rules live in `/app/docs/cmake_dependency_profile.md`, `/app/docs/input_schema.md`,
`/app/docs/precedence.md`, `/app/docs/lock_profile.md`, and
`/app/docs/report_schema.md`. Arguments are declared in `/app/src/cli.rs`.

On success write the report atomically and exit zero. On a whole-run fatal,
delete the requested report plus temp siblings, print a stderr line that starts
with `<reason_token>:`, and exit nonzero.

## Report bytes are part of the contract

On success, the report must be schema version 1. The top-level JSON object must
contain exactly these keys, in this order: `schema_version`, `request_rows`,
`declaration_rows`, `provider_rows`, `package_selection_rows`, `target_rows`,
`lock_section_rows`, `rejection_rows`, `summary`. No additional top-level key is
allowed. Encode the report as UTF-8 JSON using exactly two spaces per indentation
level. Use the row-array orders published in `/app/docs/report_schema.md`. End
the file with exactly one LF byte. Write successfully through a temporary sibling
followed by atomic replacement. On whole-run fatal, remove both the requested
report and its temporary sibling.
