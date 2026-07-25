# Report schema

Output path: `--report-out` (canonical `/app/output/resolution_report.json`).

## Serialization profile

1. The output is UTF-8 JSON.
2. No UTF-8 BOM is permitted.
3. The root value is one JSON object.
4. The root object contains exactly these nine keys:

   ```text
   schema_version
   request_rows
   declaration_rows
   provider_rows
   package_selection_rows
   target_rows
   lock_section_rows
   rejection_rows
   summary
   ```

5. The nine root keys appear in that exact order.
6. `schema_version` is the JSON integer `1`. It is not a string, float, boolean,
   or null.
7. Pretty formatting uses exactly two ASCII space characters for each nesting
   level.
8. Structural line endings are LF.
9. Tabs are not used for indentation.
10. No line has trailing spaces.
11. The completed file ends with exactly one LF byte.
12. No bytes follow that final LF.
13. Arrays use the documented semantic sort orders below.
14. Successful output uses a temporary sibling (`<path>.tmp`) and atomic
    replacement.
15. Whole-run fatal behavior removes both final and temporary outputs.

Nested object-member order policy: only the top-level object key order is
binding. Within row objects and `summary`, the exact required key set, field
types, and values are binding, but JSON member order is not independently
scored.

Compact JSON is not permitted. A missing final LF is not permitted. Extra
top-level keys are not permitted.

## Top-level object (field order)

```text
schema_version
request_rows
declaration_rows
provider_rows
package_selection_rows
target_rows
lock_section_rows
rejection_rows
summary
```

`schema_version` is integer `1`.

## `request_rows`

One row per configure request, ascending `request_index`.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `request_index` | int |
| `project_id` | string |
| `provider_config_id` | string |
| `lock_mode` | string |
| `action` | `reuse_resolution` \| `update_resolution` \| `reject_configuration` |
| `resolved_dependency_count` | int |
| `reused_section_count` | int |
| `updated_section_count` | int |

## `declaration_rows`

One row per declaration that belongs to any processed configure request's
`project_id`. Sort by `(project_id, declaration_index, declaration_id)`.

| Field | Type |
|---|---|
| `declaration_id` | string |
| `project_id` | string |
| `dependency_name` | string | normalized |
| `declaration_index` | int |
| `ownership` | `owner` \| `shadowed` |
| `override_find_package` | bool |
| `find_package_args_enabled` | bool |

## `provider_rows`

One row per find request that consulted or skipped the provider. Sort by
`(configure_request_id, find_request_id)`.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `find_request_id` | string |
| `dependency_name` | string |
| `intercepted` | bool |
| `bypass_provider` | bool |
| `response_id_or_null` | string\|null |
| `satisfies_or_null` | bool\|null |
| `outcome` | `provider_resolved` \| `provider_declined` \| `provider_skipped` \| `no_response` |

Do not use invented values such as `satisfied`, `skipped`, `resolved`, or
`declined`.

### `provider_resolved`

Use only when:

- provider interception occurred
- a response was selected
- `response.satisfies = true`
- version validation passed
- component validation passed
- the provider became the final source

### `provider_declined`

Use when:

- a response was selected with `satisfies = false`

or:

- a response claimed `satisfies = true` but failed version or component
  validation

### `provider_skipped`

Use when provider interception was not attempted because of an applicable public
skip condition, including:

- `bypass_provider`
- provider interception disabled
- a successfully selected active source override

### `no_response`

Use when:

- provider interception was attempted
- no matching response existed

## `package_selection_rows`

One row per find request. Sort by `(configure_request_id, find_request_id)`.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `find_request_id` | string |
| `dependency_name` | string |
| `source_kind` | `override` \| `provider` \| `package` \| `fetchcontent` \| `not_found` |
| `identity_or_null` | string\|null |
| `version_or_null` | string\|null |
| `components` | string[] | sorted |

## `target_rows`

One row per `(configure_request_id, dependency_name, target_id)` in any
closure. Sort by `(configure_request_id, dependency_name, target_id)`.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `dependency_name` | string |
| `target_id` | string |
| `role` | `root` \| `transitive` |
| `producer_dependency` | string |

## `lock_section_rows`

One row per section evaluated for each dependency touched by a configure
request. Sort by
`(configure_request_id, dependency_name, section_order)` where section_order is
declaration=0, provider=1, package_selection=2, target_graph=3,
final_resolution=4.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `dependency_name` | string |
| `section` | string |
| `input_digest` | string |
| `result_digest` | string |
| `disposition` | `reused` \| `updated` \| `rejected_stale` |

## `rejection_rows`

Sort by `(configure_request_id, find_request_id_or_null, reason_token)`.

When `find_request_id_or_null` is `null`, sorting treats it as an empty string,
so `null` sorts before every nonempty `find_request_id`.

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `find_request_id_or_null` | string\|null |
| `reason_token` | string |
| `message` | string |

Per-request reason tokens:

```text
unresolved_dependency
version_mismatch
components_unsatisfied
stale_lock_section
```

## `summary`

| Field | Type |
|---|---|
| `configure_request_count` | int |
| `reuse_count` | int |
| `update_count` | int |
| `reject_count` | int |
| `declaration_owner_count` | int |
| `target_row_count` | int |
