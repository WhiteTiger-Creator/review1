# Runbook Release Profile

Behavior contract for the `vault-maze-lock` release-lock compiler. It defines every input format, validation rule, ordering rule, and reason token the candidate binary must implement. Simplifications relative to full-scale automation systems are labeled Bounded task profile.

## Invocation and inputs

The planner is the Rust binary produced from the Cargo project at `/app`. Rebuilds use an offline locked release build. Invoke with absolute paths:

```
/app/target/release/vault-maze-lock \
  --runbooks /app/data/runbooks \
  --release-config /app/data/release.toml \
  --api-contract /app/data/flask_api_contract.json \
  --database /app/data/vault_maze.db \
  --requests /app/data/release_requests.ndjson \
  --output /app/output/release_report.json
```

Supported inputs:

| Input | Format | CLI flag |
|-------|--------|----------|
| Runbook directory | one YAML 1.1 mapping document per `*.yaml` file | `--runbooks` |
| Release profile | TOML 1.0.0 table | `--release-config` |
| Flask API contract | JSON object | `--api-contract` |
| Deployment registry | SQLite 3 database, opened read-only | `--database` |
| Release requests | NDJSON (one JSON object per line) | `--requests` |
| Release report | canonical JSON (written by this program) | `--output` |

All five input paths are required. The program never writes to any input path and never mutates the SQLite database or calls the Flask service. It reads `/app/data/` inputs and writes only the single JSON file at `--output`.

The candidate reads `/app/data/flask_api_contract.json` purely as a static compatibility contract. It never calls the Flask service over HTTP. The Flask application under `/app/service/` is deployment infrastructure that exposes the same routes described in the contract for realism; it is not part of the candidate solution and must not be invoked, imported, or shelled out to by the release-lock compiler.

## Runbook and release-profile data

YAML runbook subset (Bounded task profile)

Only plain YAML mappings and block sequences of scalars/mappings are supported. Anchors, aliases, tags, and flow collections are not required to parse. Each runbook file holds exactly one top-level mapping with exactly these keys, in any key order on disk:

`runbook_id`, `version`, `checksum_sha256`, `plan_rank`, `requires`, `conflicts`, `replaces`, `provides_runbook_ids`, `allowed_api_revisions`, `allowed_database_revisions`, `steps`.

Any unknown key anywhere in a runbook mapping is a fatal input error. `requires`, `conflicts`, `replaces`, `provides_runbook_ids`, `allowed_api_revisions`, and `allowed_database_revisions` are arrays of strings that must not contain duplicate values. `plan_rank` is an integer used only for deterministic tie-breaking. `steps` is a non-empty sequence; an empty `steps` array is fatal.

Runbook files are discovered by sorting file names in ascending UTF-8 byte order inside `--runbooks`; only files with a `.yaml` extension are read. A duplicate `runbook_id` across two files is a fatal input error.

Each step mapping has exactly these keys: `step_id`, `step_rank`, `step_kind`, `requires_step_ids`, `required_capabilities`, `provided_capabilities`, `api_operation_id_or_null`, `http_method_or_null`, `request_content_type_or_null`, `accepted_statuses`, `database_action_or_null`, `retry_mode`, `idempotency_key_source_or_null`. Unknown keys are fatal.

`step_kind` is one of `local_prepare`, `local_finalize`, `api_request`, `database_read`, `database_write`. Any other token is a fatal `invalid step-kind token` error.

Field combination rules:
- If `step_kind = api_request`: `api_operation_id_or_null`, `http_method_or_null`, and `request_content_type_or_null` must all be non-null, `accepted_statuses` must be non-empty, and `database_action_or_null` must be null.
- For every other `step_kind`: `api_operation_id_or_null`, `http_method_or_null`, and `request_content_type_or_null` must be null and `accepted_statuses` must be empty.

Violating either rule is a fatal `invalid step field combination` error. `requires_step_ids`, `required_capabilities`, and `provided_capabilities` must not contain duplicate values within a single step. Duplicate `step_id` values within one runbook are fatal.

TOML release profile subset

`--release-config` is a single TOML table with exactly these keys: `release_profile_version`, `maximum_runbooks_per_request`, `maximum_steps_per_batch`, `supported_api_revisions`, `supported_database_revisions`, `allowed_retry_modes`, `allowed_execution_modes`, `required_checksum_algorithm`, `canonical_json_format`, `replacement_preferences`. Unknown top-level keys are fatal. `replacement_preferences` is a table mapping a superseded `runbook_id` to its replacement `runbook_id`; every other listed field is a string or an array of strings as named.

## Checksums and stored deployment state

Runbook checksum procedure

`checksum_sha256` must equal the SHA-256 hex digest (64 lowercase hex characters) of a canonical JSON payload built from the runbook, independent of on-disk field order:

1. Build an object with keys in this fixed order: `runbook_id`, `version`, `plan_rank`, `requires`, `conflicts`, `replaces`, `provides_runbook_ids`, `allowed_api_revisions`, `allowed_database_revisions`, `steps`.
2. Sort every one of `requires`, `conflicts`, `replaces`, `provides_runbook_ids`, `allowed_api_revisions`, and `allowed_database_revisions` by ascending UTF-8 byte order.
3. Sort `steps` by ascending UTF-8 byte order of `step_id`. Each step object uses the fixed key order `step_id`, `step_rank`, `step_kind`, `requires_step_ids`, `required_capabilities`, `provided_capabilities`, `api_operation_id_or_null`, `http_method_or_null`, `request_content_type_or_null`, `accepted_statuses`, `database_action_or_null`, `retry_mode`, `idempotency_key_source_or_null`, with `requires_step_ids`, `required_capabilities`, and `provided_capabilities` each sorted by ascending UTF-8 byte order and `accepted_statuses` sorted ascending numerically.
4. Serialize with no extraneous whitespace (`,` and `:` separators only) and append exactly one `\n`.
5. Hash the UTF-8 bytes of that string with SHA-256 and hex-encode the digest in lowercase.

`checksum_sha256` values that do not match `^[0-9a-f]{64}$` are a fatal `invalid checksum syntax` error before recomputation is attempted. A runbook whose recomputed checksum does not match its declared `checksum_sha256` is a fatal `runbook_checksum_mismatch` error: the run aborts entirely; it does not become a per-request rejection.

Applied-runbook and checksum-drift semantics

The deployment registry (SQLite) records, per deployment, which `runbook_id`s have an applied checksum. For a runbook in the effective set:
- No stored entry: `checksum_status = not_applied`, `already_applied = false`, `executable = true`.
- Stored checksum equals the runbook's own `checksum_sha256`: `checksum_status = matched`, `already_applied = true`, `executable = false`.
- Stored checksum differs from the runbook's own `checksum_sha256`: this is checksum drift. For selection-time gating this is a fatal-to-the-request `applied_checksum_drift`; if it is reported in `selected_runbook_rows` it is normalized to `checksum_status = not_applied` (drift is never surfaced as a distinct row status).

A deployment's initial capability set is its stored `database_capabilities` union the `provided_capabilities` of every applied runbook whose stored checksum still matches that runbook's current checksum (drifted applied runbooks do not contribute capabilities).

Report index bases:
- `batch_index`: zero-based (first batch is `0`)
- `global_step_position`: one-based (first executed step is `1`)
- `topological_position_or_null`: one-based when present (assigned only to executable runbooks; `null` when already applied)

There is no `runbook_index`, `step_index`, or `phase_index` field in this report schema. Index values are contiguous within their documented scope unless the schema explicitly states otherwise.

## Dependency closure and replacements

Dependency closure and cycle detection

For a release request with `target_runbook_ids`, the selected set is the transitive closure of `requires` starting from the direct targets. Any referenced `runbook_id` that does not exist in the loaded runbook set is `missing_dependency`. If the induced subgraph over the selected set contains a cycle, the run reports `dependency_cycle`; the reported `cycle_members` is the lexicographically-smallest strongly connected component of size greater than one, with members sorted by ascending UTF-8 byte order.

For `missing_dependency`:
- `runbook_id_or_null` contains the runbook ID of the missing dependency (not the requester).
- The requesting runbook ID is not placed in `details.related_ids` for this reason (`related_ids` stays `[]`).
- The release / request identity remains `request_id` on the rejection row.

Synthetic non-fixture example: runbook `alpha` requires runbook `beta`; `beta` is absent; `runbook_id_or_null = "beta"`.

Preferred replacement scope

Preferred replacement is considered only for a runbook that entered the candidate plan as a non-direct-target dependency.

Definitions:
- direct target: a runbook explicitly requested by the release input (`target_runbook_ids`).
- dependency-selected runbook: a runbook introduced only because another selected runbook requires it.

A runbook explicitly named as a release target is never replaced. This remains true even when a valid preferred replacement exists, the replacement provides the same capability, the replacement would otherwise be compatible, the replacement has a later revision, or the replacement is marked preferred.

When a runbook is both directly requested and also reachable as a dependency, direct-target status wins. It remains selected as `selection_reason = "requested"` and is not replaced. Do not emit `target`, `direct_target`, `replacement`, or `dependency` for a directly requested row. Direct-target identity must be retained through replacement resolution.

Replacement resolution (dependency-only)

After closure and drift checks (see failure precedence below), each entry in `replacement_preferences` (old_id mapped to new_id) is applied when `old_id` is in the selected set and was not a direct target of the request. The replacement is accepted only when all of the following hold, otherwise the request fails with `replacement_unsatisfied`:
- `new_id` exists among the loaded runbooks.
- `new_id.replaces` contains `old_id` and `new_id.provides_runbook_ids` contains `old_id`.
- `new_id.allowed_api_revisions` contains the request's `target_api_revision`.
- `new_id.allowed_database_revisions` contains the request's `target_database_revision`.

If `old_id` or `new_id` already has applied-checksum drift against the target deployment, the failure is `applied_checksum_drift` (checked before `replacement_unsatisfied` for that pair). Accepting a replacement swaps `old_id` for `new_id` in the effective set, records the mapping for `replaces_runbook_ids` and `selection_reason = "replacement"`, and pulls in the transitive closure of `new_id.requires` (a missing dependency here is also `missing_dependency`).

Outcome summary for a preference pair:
- not considered: `old_id` absent from selected set, or `old_id` is a direct target
- selected / valid: all acceptance conditions above hold
- rejected `applied_checksum_drift`: `old_id` or `new_id` has checksum drift
- rejected `replacement_unsatisfied`: any other acceptance condition fails
- rejected `missing_dependency`: replacement's transitive `requires` names an unknown runbook

Replacement dependency edges

A dependency relationship satisfied through a selected replacement is not reported as an ordinary `requires` edge to the replacement. The canonical dependency-edge token is `replacement_provides`.

For such an edge:
- `from_runbook_id` is the requiring runbook (the source of the original `requires` entry).
- `to_runbook_id` is the replaced dependency identity as written in that `requires` list.
- `satisfied_by_runbook_id` is the selected replacement identity.
- `edge_type` is `"replacement_provides"`.

Ordinary dependency edges use `"requires"` with `satisfied_by_runbook_id == to_runbook_id`. The two tokens are not interchangeable. Do not emit a second edge for the same satisfied relationship.

Ordering-edge set (canonical)

A replacement relationship affects runbook selection and dependency satisfaction. It does not, by itself, create a topological ordering edge between the replaced runbook, the selected replacement runbook, or the runbook that caused the replacement to be considered. Replacement provenance is not an ordering dependency.

Distinguish:
- Selection / provenance: preference pairs, `selection_reason = "replacement"`, and `replaces_runbook_ids`. These record why a runbook entered the effective set. They do not participate in topological ordering.
- Ordering edges: the only edges used when topologically sorting selected runbooks for execution.

For every runbook `R` in the effective set and every `raw_dep` in `R.requires`:
1. Let `satisfied = replacement_map[raw_dep]` when `raw_dep` was replaced, otherwise `satisfied = raw_dep`.
2. If `satisfied` is also in the effective set, emit exactly one ordering edge from `satisfied` before `R` (dependency before depender).

Relationship participation:
- Ordinary `requires` (no replacement): yes; edge from dep before `R`
- `requires` retargeted through a selected replacement: yes; edge from replacement before `R` (same rule)
- Report row `edge_type = "replacement_provides"`: report labeling only; the ordering constraint is the retargeted edge above, not an extra edge
- Replacement preference / provenance (`replaces_runbook_ids`): no
- `selection_reason = "replacement"`: no

Do not add an ordering edge merely because a replacement runbook replaces another.

When a selected replacement satisfies a `requires` entry, the ordinary dependency obligation is retargeted to the replacement for ordering: the edge becomes replacement before requiring_runbook. The report records that satisfaction as `edge_type = "replacement_provides"` with `to_runbook_id` still equal to the original dependency identity. No additional provenance-only ordering edge is emitted.

Deterministic zero-indegree tie-break

When multiple selected runbooks have indegree zero in the ordering DAG, dequeue the next runbook by this key, in order:
1. ascending `plan_rank` (integer)
2. ascending UTF-8 byte order of `runbook_id`

Re-sort the ready set with that key after every dequeue. Outgoing adjacency is traversed in ascending UTF-8 byte order of the successor `runbook_id`.

Synthetic non-fixture example:
- Runbook `alpha` requires `legacy`.
- Preference replaces `legacy` with `safe`; `safe` is selected with provenance recorded.
- Ordering edges: retarget `legacy` so the edge is `safe` before `alpha`. Also include any real `requires` of `safe`.
- No edge is added solely because `safe` replaces `legacy`.
- Ready-set ties break by `plan_rank`, then `runbook_id` UTF-8 order.

Conflict detection

After replacement resolution, if any runbook in the effective set lists another effective-set member in its `conflicts` array, the request fails with `selected_runbook_conflict`.

## API and database compatibility

- `target_api_revision` must appear in the release profile's `supported_api_revisions`, else `unknown_api_revision`.
- `target_database_revision` must appear in `supported_database_revisions`, else `database_revision_mismatch`.
- The target deployment's stored `database_revision` must equal the request's `target_database_revision`, else `database_revision_mismatch`. For this reason token, `details.actual_or_null` and `details.expected_or_null` are always JSON `null` (see Rejection detail nullability in `/app/docs/report_schema.md`).
- Every runbook in the effective set must list the request's `target_api_revision` in its own `allowed_api_revisions` (else `runbook_api_revision_forbidden`) and the request's `target_database_revision` in its own `allowed_database_revisions` (else `runbook_database_revision_forbidden`).
- Every `api_request` step's `api_operation_id_or_null` must resolve to an operation in the Flask API contract keyed by `(target_api_revision, operation_id)`, else `unknown_api_operation`.
- The step's `http_method_or_null`, normalized by trimming whitespace, requiring an alphabetic-only token, and upper-casing, must equal the resolved operation's `method`, else `api_method_mismatch` (details record the operation's method as expected and the normalized step method as actual).
- The step's `request_content_type_or_null`, normalized by trimming and lower-casing (a value containing `;` normalizes to invalid), must appear in the operation's `accepted_request_content_types`, else `api_content_type_mismatch`.
- The step's `accepted_statuses` must be a subset of the operation's `success_statuses`, else `api_success_status_mismatch`.

## Capabilities, ordering, and batching

Step graph validation

Within one runbook: a step listing its own `step_id` in `requires_step_ids` is `invalid_step_dependency`, as is a `requires_step_ids` entry that does not name another step in the same runbook, and a dependency cycle among the runbook's own steps (smallest strongly connected component reported the same way as runbook cycles).

Scheduling order

Steps execute in an order that is a topological sort of `requires_step_ids` within each runbook (ties broken by ascending `step_rank`, then ascending UTF-8 byte order of `step_id`), and runbooks execute in an order that is a topological sort of the effective dependency graph using only the canonical ordering-edge set above (ties broken by ascending `plan_rank`, then ascending UTF-8 byte order of `runbook_id`). Only executable runbooks (not already applied) contribute steps. Scheduled execution order drives `step_rows` and `batch_rows`; it does not assign `selected_runbook_rows.topological_position_or_null` (see `/app/docs/report_schema.md`).

Capability availability (validation / simulation)

Every step's `required_capabilities`, plus (for `api_request` steps) the resolved operation's `required_capabilities`, must already be available: either from the deployment's initial capability set or from a capability produced earlier in the same simulated run. A missing capability that no earlier step in the run produces is `missing_database_capability`. A missing capability that is produced later in the same batch as the step that needs it is instead `capability_producer_order_invalid` (capabilities become available only once their producing batch has closed).

Required capability projection (report fields)

`batch_rows.required_capabilities` and `step_rows.required_capabilities` contain only capabilities that remain unsatisfied relative to the initial applied deployment state. They are not a copy of every capability used during compatibility validation. Selected-runbook rows do not carry a `required_capabilities` field.

Before any batch is constructed, every capability already present in the initial applied deployment state is considered satisfied for report projection. Such a capability must not appear in any reported `required_capabilities` array merely because a selected runbook declares it as a requirement.

Bounded projection operation:
1. Normalize declared capability identities using the existing public rule (exact UTF-8 strings; no case folding; no trimming).
2. Deduplicate them (first-seen order during collection).
3. Subtract capabilities satisfied by the initial applied state (deployment `database_capabilities` union `provided_capabilities` of every applied runbook whose stored checksum still matches).
4. Apply the existing documented producer-visibility rule: capabilities produced later in the same plan remain in reported `required_capabilities` when declared; they are used only for availability simulation and batch-boundary decisions, not for subtracting report projection. Do not invent same-batch or earlier-batch producer subtraction for report rows.
5. Sort the remaining identities by ascending UTF-8 byte order.
6. Serialize an empty result as `[]`.

Do not retain a capability merely to explain why a runbook was selected. Selection provenance and unsatisfied capability projection are separate report concepts. Initial capabilities must be loaded before reported requirement projection.

### Worked required-capabilities example

This example uses synthetic, non-fixture identifiers. It distinguishes capabilities used for compatibility validation from capabilities projected into report rows.

Initial applied capabilities:

```
cap:api-session
cap:database-ready
```

Step declaration (`step.required_capabilities`):

```
cap:database-ready
cap:runbook-local
```

Resolved Flask operation (`operation.required_capabilities`):

```
cap:api-session
cap:remote-route
```

Compatibility validation

For an `api_request` step, capability availability validation checks the union of:
- the step's declared `required_capabilities`; and
- the resolved Flask operation's `required_capabilities`.

The validation set in this example is:

```
cap:api-session
cap:database-ready
cap:remote-route
cap:runbook-local
```

The initial state already satisfies `cap:api-session` and `cap:database-ready`. The remaining requirements still need to be available through the plan: `cap:remote-route` and `cap:runbook-local`.

Step report projection

`step_rows.required_capabilities` is projected from the step's declared `required_capabilities` only.

Flask operation required capabilities participate in compatibility validation, but they are not copied into the step report field unless the same identity is also declared by the step.

The step report result is therefore:

```json
["cap:runbook-local"]
```

because `cap:database-ready` was present in the initial applied state. The report does not add `cap:api-session` or `cap:remote-route` from the Flask operation.

Batch report projection

`batch_rows.required_capabilities` starts from the union of the batch's step declarations, not from the union of Flask operation requirements.

For a batch containing only the example step, the result is:

```json
["cap:runbook-local"]
```

In-plan production rule

If an earlier batch in the same new plan produces `cap:runbook-local`, that capability is available for execution simulation after the producer batch closes.

It still remains in the reported `required_capabilities` array.

Only the initial applied deployment capability set is subtracted from report projection fields.

Empty projection

If the step declared only `cap:database-ready`, the projected result would be:

```json
[]
```

Execution batching

Steps are grouped into ordered batches. A new batch starts whenever any of the following is true for the next step relative to the currently open batch:
- the execution mode changes (`local`, `api_request`, or `database_transaction`, derived from `step_kind`);
- the open batch has already reached `maximum_steps_per_batch` steps;
- the next step's mode is `api_request` (every `api_request` step is isolated in its own batch);
- the next step's `retry_mode` is `idempotency_key_required` (also isolated); or
- the next step requires a capability that the open batch itself already produced (a capability cannot be consumed in the same batch that produces it).

Each closed batch reports the union of its steps' runbook IDs (first-seen order), step IDs (execution order), required and produced capabilities (each sorted by ascending UTF-8 byte order), and a batch-level `retry_mode` of `safe` only when every step in a `local` or `database_transaction` batch used `safe`, otherwise `never` (an `api_request` or `idempotency_key_required` batch keeps the mode of its single step).

## Retry rules

Allowed `retry_mode` values are `never`, `safe`, and `idempotency_key_required`, subject to step-kind restrictions:

| `step_kind` | Allowed `retry_mode` |
|-------------|----------------------|
| `local_prepare`, `local_finalize` | `never`, `safe` |
| `database_read` | `never`, `safe` |
| `database_write` | `never` only |
| `api_request` | `never`, `safe`, `idempotency_key_required` |

`idempotency_key_required` is only ever valid on `api_request` steps. An `api_request` step using `retry_mode = safe` is invalid unless the resolved operation is `idempotent = true`. An `api_request` step using `retry_mode = idempotency_key_required` must have a non-null `idempotency_key_source_or_null`, else `missing_idempotency_key_source`. Any other violation is `invalid_retry_policy`.

## Rejections and fatal errors

Fatal input errors versus per-request rejections

A fatal input error aborts the entire run before any request is processed: malformed YAML/TOML/JSON/NDJSON, unknown fields, duplicate unique-array values, invalid checksum syntax, a runbook checksum mismatch, an unexpected SQLite schema, a foreign deployment reference, or an invalid stored checksum. On a fatal error the program exits non-zero, prints a message to stderr, and removes any stale `--output` file; no report is written.

A per-request rejection affects only that request: the run continues, the report is written, and the rejected request contributes a `rejected` `request_rows` entry plus one `rejection_rows` entry. All count fields on a rejected `request_rows` entry are zero.

Failure precedence (Bounded task profile)

For a single request, checks are evaluated in this exact order and the first triggered check determines the reason token; later checks are never reached once an earlier one fails:

1. `unknown_deployment`
2. `unknown_target_runbook`
3. `missing_dependency`
4. `dependency_cycle`
5. `applied_checksum_drift`
6. `replacement_unsatisfied`
7. `selected_runbook_conflict`
8. `unknown_api_revision`
9. `runbook_api_revision_forbidden`
10. `unknown_api_operation`
11. `api_method_mismatch`
12. `api_content_type_mismatch`
13. `api_success_status_mismatch`
14. `database_revision_mismatch`
15. `runbook_database_revision_forbidden`
16. `invalid_step_dependency`
17. `missing_database_capability`
18. `capability_producer_order_invalid`
19. `invalid_retry_policy`
20. `missing_idempotency_key_source`
21. `batch_construction_failed`

Same-reason deterministic selection

When multiple violations of the same reason token exist for one request, select exactly one using this tie-break (it does not reorder the cross-reason precedence list above):

1. Use canonical executable runbook order.
2. Within one runbook, use `step_rank` ascending and then `step_id` by UTF-8 bytes.
3. For runbook-scoped checks, select the first offending runbook in canonical runbook order (ascending UTF-8 byte order of `runbook_id` over the applicable set).
4. For step-scoped checks evaluated before local step-graph validation, this tie-break does not depend on `requires_step_ids`.

Do not let HashMap, HashSet, YAML-file, or physical row order choose a different rejection identity.

Same-reason selection examples (synthetic IDs; request-array order, requires-array order, TOML preference order, and hash-container order do not choose the identity):

1. Multiple unknown direct targets. A request with `target_runbook_ids: ["missing-zeta", "missing-alpha"]` rejects with `unknown_target_runbook` and `runbook_id_or_null = "missing-alpha"`. Reversing the request array still selects `"missing-alpha"`.

2. Multiple missing dependency edges. Reachable runbook `syn-alpha` requires `missing-zeta` and reachable runbook `syn-beta` requires `missing-alpha`. The selected missing identity is `missing-zeta` because requesting-runbook UTF-8 order chooses `syn-alpha` first. Reversing requires-array order or on-disk runbook file order does not change that identity.

3. Multiple unsatisfied replacement pairs. Applicable preferences `z-old = z-new` and `a-old = a-new` are both `replacement_unsatisfied`. The selected identity is `a-old` with `details.related_ids = ["a-old", "a-new"]` even when the TOML table physically lists `z-old` first.

Rejection identity fields

`runbook_id_or_null` identifies the runbook that owns or directly triggers the rejected condition.

`step_id_or_null` identifies the exact step when the condition is step-scoped.

A missing dependency is identified by the missing dependency ID, not by the requesting runbook.

A runbook-scoped compatibility failure uses the offending runbook ID and a null step ID.

An API, capability, or retry failure uses both the offending runbook and step.

A local step cycle identifies the runbook but has no single offending step, so `step_id_or_null` is null.

The complete normative nullability matrix for `runbook_id_or_null`, `step_id_or_null`, and all `details.*` fields is in `/app/docs/report_schema.md` under Rejection identity and detail matrix.

Reason-token stage map

Every reason token maps to exactly one `stage` value reported in `rejection_rows`:

| Stage | Reason tokens |
|-------|----------------|
| `deployment` | `unknown_deployment` |
| `target` | `unknown_target_runbook` |
| `dependency` | `missing_dependency` |
| `graph` | `dependency_cycle` |
| `checksum` | `applied_checksum_drift` |
| `replacement` | `replacement_unsatisfied` |
| `conflict` | `selected_runbook_conflict` |
| `api` | `unknown_api_revision`, `runbook_api_revision_forbidden`, `unknown_api_operation`, `api_method_mismatch`, `api_content_type_mismatch`, `api_success_status_mismatch` |
| `database` | `database_revision_mismatch`, `runbook_database_revision_forbidden` |
| `step_graph` | `invalid_step_dependency` |
| `capability` | `missing_database_capability`, `capability_producer_order_invalid` |
| `retry` | `invalid_retry_policy`, `missing_idempotency_key_source` |
| `batching` | `batch_construction_failed` |

Planning phase boundaries

Observable semantic order only (no prescribed modules, structs, graph libraries, or database abstractions):

1. Parse and structurally validate all bounded input files.
2. Load the initial applied deployment and capability state.
3. Identify direct release targets.
4. Expand dependency closure.
5. Apply preferred replacement only to eligible non-direct-target dependencies.
6. Resolve conflicts and compatibility.
7. Compute accepted and rejected release decisions.
8. Derive capability producers and ordering.
9. Validate local step dependencies.
10. Build deterministic runbook and step order.
11. Construct batches.
12. Project report rows and summaries (including required-capability subtraction against the initial applied state).
