# Release Report

This document defines the exact output schema for `/app/output/release_report.json`, the single artifact written by `vault-maze-lock`.

## Output file and serialization

- Valid UTF-8 JSON, no BOM.
- Two-space pretty-printed JSON (`canonical_json_format = "pretty-2-lf"` in the release profile).
- Exactly one trailing LF (`0x0A`) and no additional trailing whitespace.
- Write atomically: content goes to a temporary file in `/app/output/`, then rename onto the final path.
- On a whole-run fatal failure, remove any stale `/app/output/release_report.json` and leave no temporary file behind.
- Two successful runs over identical inputs must produce byte-identical output.
- Recursive alphabetical key sorting is not required beyond the explicit field orders below.

## Top-level object

A single JSON object with exactly these top-level keys, in this order, and no additional keys:

1. `request_rows`
2. `selected_runbook_rows`
3. `dependency_edge_rows`
4. `step_rows`
5. `batch_rows`
6. `rejection_rows`
7. `summary`

Canonical tokens are case-sensitive. Synonyms are not accepted. Human-readable equivalents are not accepted. Do not derive output tokens from enum variant names or internal labels.

- `selection_reason`: `"requested"`, `"replacement"`, `"dependency"`
- dependency `edge_type`: `"requires"`, `"replacement_provides"`
- `status`: `"accepted"`, `"rejected"`
- `execution_mode`: `"local"`, `"api_request"`, `"database_transaction"`
- `step_kind`: `"local_prepare"`, `"local_finalize"`, `"api_request"`, `"database_read"`, `"database_write"`
- `checksum_status`: `"not_applied"`, `"matched"`
- rejection `reason`: see failure precedence in `/app/docs/runbook_release_profile.md`
- rejection `stage`: see reason-token stage map in `/app/docs/runbook_release_profile.md`

## Accepted-request rows

request_rows

Fields, in serialized order:
- `request_id`: string
- `deployment_id`: string
- `target_api_revision`: string
- `target_database_revision`: string
- `status`: `"accepted"` | `"rejected"`
- `reason_or_null`: string | null
- `selected_runbook_count`: integer
- `executable_runbook_count`: integer
- `executable_step_count`: integer
- `batch_count`: integer

Emission:
- One row per input release request.
- For a rejected request, `reason_or_null` holds the first triggered failure reason token and every count field is `0`.

Sort:
- `request_id`, ascending UTF-8 byte order.

selected_runbook_rows

Emitted only for accepted requests, one row per runbook in that request's effective set.

Fields, in serialized order:
- `request_id`: string
- `runbook_id`: string
- `selection_reason`: `"requested"` | `"replacement"` | `"dependency"`
- `checksum_status`: `"not_applied"` | `"matched"`
- `already_applied`: boolean
- `executable`: boolean
- `topological_position_or_null`: integer | null
- `replaces_runbook_ids`: array of strings

Notes:
- `topological_position_or_null` is a 1-based index assigned only to executable runbooks. Walk the effective set in ascending UTF-8 byte order of `runbook_id` and assign consecutive integers `1, 2, 3, ...` to executable members in that walk order. Already-applied runbooks receive `null` and do not consume a position integer.
- This index is not the runbook's index in the scheduled dependency-DAG execution order used for `step_rows` / `batch_rows`. Do not set it from schedule order, replacement provenance, or `selection_reason`.
- `replaces_runbook_ids` lists the `runbook_id`s this row's runbook replaced, sorted by ascending UTF-8 byte order.
- A directly requested runbook uses `selection_reason = "requested"` (not `target` or `direct_target`).

Sort:
- `request_id`, then `already_applied` (`false` before `true`), then `topological_position_or_null` (integers before null, ascending), then `runbook_id` (UTF-8 byte order).

dependency_edge_rows

Emitted only for accepted requests, one row per satisfied `requires` edge within the effective set.

Fields, in serialized order:
- `request_id`: string
- `from_runbook_id`: string
- `to_runbook_id`: string
- `edge_type`: `"requires"` | `"replacement_provides"`
- `satisfied_by_runbook_id`: string

Notes:
- `to_runbook_id` is always the dependency ID as written in the source runbook's `requires` list, even when a replacement was applied.
- `satisfied_by_runbook_id` equals `to_runbook_id` for `edge_type = "requires"`, or the replacement runbook ID for `edge_type = "replacement_provides"`.
- A replacement capability satisfaction edge uses `edge_type = "replacement_provides"` (not `requires`).

Sort:
- `request_id`, `from_runbook_id`, `to_runbook_id`, `edge_type`, `satisfied_by_runbook_id` (all UTF-8 byte order).

## Execution rows

step_rows

Emitted only for accepted requests, one row per executed step across all executable runbooks in that request.

Fields, in serialized order:
- `request_id`: string
- `runbook_id`: string
- `step_id`: string
- `global_step_position`: integer (1-based)
- `step_kind`: string (`"local_prepare"`, `"local_finalize"`, `"api_request"`, `"database_read"`, or `"database_write"`)
- `execution_mode`: `"local"` | `"api_request"` | `"database_transaction"`
- `retry_mode`: string
- `api_operation_id_or_null`: string | null
- `required_capabilities`: array of strings
- `provided_capabilities`: array of strings
- `batch_index`: integer (0-based)

Notes:
- `global_step_position` numbers steps in strict execution order across the whole request, starting at 1.
- `required_capabilities` is the projected remaining set after subtracting initial applied capabilities. See Required capability projection and the Worked required-capabilities example in `/app/docs/runbook_release_profile.md`. Projection uses the step's declared `required_capabilities` only (Flask operation requirements are not copied into this field unless the same identity is also declared by the step). Sort by ascending UTF-8 byte order.
- `provided_capabilities` is sorted by ascending UTF-8 byte order.

Emission / sort:
- Rows are emitted in execution order (equivalently, sorted by `request_id` then `global_step_position`).

batch_rows

Emitted only for accepted requests, one row per execution batch.

Fields, in serialized order:
- `request_id`: string
- `batch_index`: integer (0-based)
- `execution_mode`: `"local"` | `"api_request"` | `"database_transaction"`
- `runbook_ids`: array of strings
- `step_ids`: array of strings
- `retry_mode`: string
- `required_capabilities`: array of strings
- `produced_capabilities`: array of strings

Notes:
- `runbook_ids` lists each runbook contributing to the batch in first-seen order (not sorted).
- `step_ids` lists the batch's steps in execution order (not sorted).
- `required_capabilities` is the projected remaining union of the batch's step declarations after initial-applied subtraction (not the union of Flask operation requirements). See `/app/docs/runbook_release_profile.md`. Sort by ascending UTF-8 byte order.
- `produced_capabilities` is sorted by ascending UTF-8 byte order.

Emission / sort:
- Rows are emitted in batch execution order (equivalently, sorted by `request_id` then `batch_index`).

## Rejected-request rows

rejection_rows

Exactly one row per rejected request.

Fields, in serialized order:
- `request_id`: string
- `stage`: stage token
- `reason`: reason token
- `runbook_id_or_null`: string | null
- `step_id_or_null`: string | null
- `details`: object

Allowed `stage` tokens: `deployment`, `target`, `dependency`, `graph`, `checksum`, `replacement`, `conflict`, `api`, `database`, `step_graph`, `capability`, `retry`, `batching`. See `/app/docs/runbook_release_profile.md` for the exact reason-to-stage map and failure precedence.

`details` contains exactly these four fields, serialized in ascending key order (`actual_or_null`, `cycle_members`, `expected_or_null`, `related_ids`):
- `actual_or_null`: string | null
- `cycle_members`: array of strings
- `expected_or_null`: string | null
- `related_ids`: array of strings

Unused array fields are empty arrays (never omitted); unused scalar fields are `null`. `cycle_members` and `related_ids` are each sorted by ascending UTF-8 byte order when populated. `details` never contains raw exception text or any field not listed here.

Sort:
- `request_id`, then `stage`, then `reason`, then `runbook_id_or_null` (null before string; string ties by UTF-8), then `step_id_or_null` (same null-first rule).

Rejection identity and detail matrix

Nullability is defined per rejection reason for every nullable rejection surface. A field whose matrix entry is required null must be serialized as JSON `null`. It must not contain a helpful diagnostic value even when such a value is available internally. The report contract, not diagnostic convenience, controls nullability.

The row-level identity matrix is normative.

Do not infer nullability from diagnostic convenience.

Do not leave `runbook_id_or_null` or `step_id_or_null` null when this matrix requires an identity.

Do not populate either field when this matrix requires null.

Unused array fields are empty arrays (never omitted); unused scalar fields are `null`.

### Row-level identity (`runbook_id_or_null`, `step_id_or_null`)

| Reason | `runbook_id_or_null` | `step_id_or_null` |
| ------ | -------------------- | ----------------- |
| `unknown_deployment` | null | null |
| `unknown_target_runbook` | missing target runbook ID | null |
| `missing_dependency` | missing dependency runbook ID | null |
| `dependency_cycle` | null | null |
| `applied_checksum_drift` | drifted runbook ID | null |
| `replacement_unsatisfied` | first canonical involved runbook ID | null |
| `selected_runbook_conflict` | null | null |
| `unknown_api_revision` | null | null |
| `runbook_api_revision_forbidden` | offending runbook ID | null |
| `unknown_api_operation` | offending runbook ID | offending step ID |
| `api_method_mismatch` | offending runbook ID | offending step ID |
| `api_content_type_mismatch` | offending runbook ID | offending step ID |
| `api_success_status_mismatch` | offending runbook ID | offending step ID |
| `database_revision_mismatch` | null | null |
| `runbook_database_revision_forbidden` | offending runbook ID | null |
| `invalid_step_dependency` — self-reference or missing local dependency | offending runbook ID | offending step ID |
| `invalid_step_dependency` — local step cycle | offending runbook ID | null |
| `missing_database_capability` | consuming runbook ID | consuming step ID |
| `capability_producer_order_invalid` | consuming runbook ID | consuming step ID |
| `invalid_retry_policy` | offending runbook ID | offending step ID |
| `missing_idempotency_key_source` | offending runbook ID | offending step ID |
| `batch_construction_failed` | null | null |

For `replacement_unsatisfied`:

- When validating a replacement preference pair: `runbook_id_or_null` is the old runbook ID.
- When a selected replacement has a missing transitive dependency: `runbook_id_or_null` is the replacement runbook ID.
- The canonical `related_ids` array continues to describe the complete involved pair.

### Detail fields (`details.*`)

Each line is: reason; actual_or_null; expected_or_null; cycle_members; related_ids.

- `unknown_deployment`; required null; required null; empty `[]`; empty `[]`
- `unknown_target_runbook`; required null; required null; empty `[]`; empty `[]`
- `missing_dependency`; required null; required null; empty `[]`; empty `[]`
- `dependency_cycle`; required null; required null; required non-null (sorted members); empty `[]`
- `applied_checksum_drift`; required null; required null; empty `[]`; empty `[]`
- `replacement_unsatisfied`; required null; required null; empty `[]`; conditionally non-null (related ids)
- `selected_runbook_conflict`; required null; required null; empty `[]`; empty `[]`
- `unknown_api_revision`; required null; required null; empty `[]`; empty `[]`
- `runbook_api_revision_forbidden`; required null; required null; empty `[]`; empty `[]`
- `unknown_api_operation`; required null; required null; empty `[]`; empty `[]`
- `api_method_mismatch`; required non-null (normalized step method); required non-null (operation method); empty `[]`; empty `[]`
- `api_content_type_mismatch`; required null; required null; empty `[]`; empty `[]`
- `api_success_status_mismatch`; required null; required null; empty `[]`; empty `[]`
- `database_revision_mismatch`; required null; required null; empty `[]`; empty `[]`
- `runbook_database_revision_forbidden`; required null; required null; empty `[]`; empty `[]`
- `invalid_step_dependency`; required null; required null; conditionally non-null (cycle); conditionally non-null
- `missing_database_capability`; required null; required null; empty `[]`; required non-null (capability id)
- `capability_producer_order_invalid`; required null; required null; empty `[]`; required non-null (capability id)
- `invalid_retry_policy`; required null; required null; empty `[]`; empty `[]`
- `missing_idempotency_key_source`; required null; required null; empty `[]`; empty `[]`
- `batch_construction_failed`; required null; required null; empty `[]`; empty `[]`

## Summary

Exactly these fields, in this order:
- `request_count`: integer
- `accepted_request_count`: integer
- `rejected_request_count`: integer
- `selected_runbook_count`: integer
- `executable_runbook_count`: integer
- `executable_step_count`: integer
- `local_batch_count`: integer
- `api_request_batch_count`: integer
- `database_transaction_batch_count`: integer
- `checksum_drift_count`: integer

Every summary value must be derived from the emitted rows; the program must not maintain a separate authoritative counter that could drift from the rows themselves.

Formulas (Bounded task profile):
- `request_count` = length of `request_rows`
- `accepted_request_count` = count of `request_rows` with `status = "accepted"`
- `rejected_request_count` = count of `request_rows` with `status = "rejected"`
- `selected_runbook_count` = length of `selected_runbook_rows`
- `executable_runbook_count` = count of `selected_runbook_rows` with `executable = true`
- `executable_step_count` = length of `step_rows`
- `local_batch_count` = count of `batch_rows` with `execution_mode = "local"`
- `api_request_batch_count` = count of `batch_rows` with `execution_mode = "api_request"`
- `database_transaction_batch_count` = count of `batch_rows` with `execution_mode = "database_transaction"`
- `checksum_drift_count` = count of `rejection_rows` with `reason = "applied_checksum_drift"`

## Sorting and determinism

- Row sort keys are stated under each row type above.
- Array fields that the schema marks as sorted use ascending UTF-8 byte order unless noted otherwise (`runbook_ids` and `step_ids` in batches are intentional exceptions).
- Two successful runs over identical inputs must produce byte-identical output.

## Fatal cleanup

`--output` is written to a sibling `*.json.tmp` file in the same directory, flushed and synced, then renamed onto the final path. If the run fails with a fatal input error, the program removes any file already present at `--output` before exiting, so a previous successful run's report is never mistaken for the result of a failed run. No `.tmp` file is left behind by either a successful run or a fatal failure.
