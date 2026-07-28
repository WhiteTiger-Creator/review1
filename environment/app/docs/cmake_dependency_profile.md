# Bounded CMake-inspired dependency profile

This task implements a **bounded CMake-inspired dependency-provider and
FetchContent reconciliation profile**. It does not claim full CMake
compatibility. CMake is never executed.

## Units of work

Process every configure request listed in `policy.json` `configure_requests`
in ascending `request_index` order. Each request selects a `project_id`, a
`provider_config_id`, a `lock_mode` (`error` or `update`), and a prior lock
object id (nullable).

## Dependency name normalization

For declaration ownership and override lookups, dependency names compare
case-insensitively after trimming ASCII whitespace. The canonical stored form is
ASCII-lowercase. Target identities are exact UTF-8 strings and are never
case-folded.

## Version model

Versions are exactly one of:

```text
N
N.N
N.N.N
```

Normalize to three non-negative integers `(major, minor, patch)` by appending
zeros. Reject any other version string as `invalid_version`.

Matching modes:

| Mode | Rule |
|---|---|
| minimum | candidate version ≥ requested version lexicographically by component |
| exact | candidate version equals requested version on all three components |

Package candidates declare `compatibility`:

| Value | Rule |
|---|---|
| `exact` | only exact version matches |
| `same_major` | major equal; minor/patch ignored for minimum requests; exact still exact |
| `same_minor_or_newer` | major+minor equal and candidate patch ≥ request patch for minimum; exact still exact |

When the request has `version_or_null = null`, any candidate version is accepted
for version purposes (components still apply).

When the request has `exact = true`, treat the request as exact-mode regardless
of candidate compatibility label; the candidate must still satisfy its own
compatibility constraints against that exact version (i.e. candidate version
must equal the request version).

When the request has `exact = false` and a version is set, treat as minimum-mode
filtered by the candidate's compatibility label:

- `exact` candidates only match if versions are equal
- `same_major` candidates match if majors equal and candidate ≥ request
- `same_minor_or_newer` candidates match if major+minor equal and candidate ≥ request

## Components

`components` arrays are semantic sets. Sort unique UTF-8 ascending for digests
and report emission. A provider result or package candidate satisfies a request
only when every required component is listed in `provided_components`.

## Source kinds

Declaration `source_kind` is exactly: `archive`, `git`, or `local`.

## Fatal whole-run tokens

Whole-run fatals (delete outputs, nonzero exit):

```text
missing_required_input
malformed_json
invalid_input_schema
duplicate_declaration_index
duplicate_find_request_index
duplicate_configure_request_index
unknown_reference
invalid_version
conflicting_declaration_flags
duplicate_target_producer
unknown_target_reference
target_dependency_cycle
```

Per-request rejections use `rejection_rows` with tokens listed in
`report_schema.md` and still allow the process to continue other requests.
Exit remains zero when no whole-run fatal occurred.
