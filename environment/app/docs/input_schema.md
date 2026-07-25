# Input schema

All paths are under the selected `--data-dir` (default `/app/data`).

## `declarations.json`

```json
{
  "declarations": [ Declaration, ... ]
}
```

Declaration fields (all required unless noted):

| Field | Type | Rules |
|---|---|---|
| `declaration_id` | string | nonempty, unique globally |
| `project_id` | string | nonempty |
| `dependency_name` | string | nonempty |
| `declaration_index` | integer | ≥ 0; unique within `project_id` |
| `source_kind` | string | `archive` \| `git` \| `local` |
| `source_identity` | string | nonempty |
| `declared_version_or_null` | string\|null | null or valid version |
| `override_find_package` | bool | — |
| `find_package_args` | object | see below |
| `produced_targets` | string[] | unique; sorted in reports |
| `content_digest` | string | 64 lowercase hex SHA-256 |

`find_package_args`:

| Field | Type |
|---|---|
| `enabled` | bool |
| `try_system_first` | bool |
| `components` | string[] |
| `version_or_null` | string\|null |

Duplicate `declaration_index` within one project → whole-run
`duplicate_declaration_index`.

## `find_requests.ndjson`

One JSON object per line. Fields:

| Field | Type | Rules |
|---|---|---|
| `find_request_id` | string | unique |
| `project_id` | string | — |
| `dependency_name` | string | — |
| `request_index` | integer | unique within project |
| `required` | bool | — |
| `exact` | bool | — |
| `version_or_null` | string\|null | — |
| `components` | string[] | — |
| `bypass_provider` | bool | — |
| `request_kind` | string | `find_package` \| `make_available` |

Duplicate `request_index` within one project → `duplicate_find_request_index`.

## `provider_responses.json`

```json
{
  "providers": [ ProviderConfig, ... ],
  "responses": [ ProviderResponse, ... ]
}
```

ProviderConfig:

| Field | Type |
|---|---|
| `provider_config_id` | string |
| `intercept_find_package` | bool |
| `intercept_fetchcontent` | bool |

ProviderResponse:

| Field | Type |
|---|---|
| `response_id` | string |
| `provider_config_id` | string |
| `dependency_name` | string |
| `request_kind` | string | `find_package` \| `make_available` |
| `satisfies` | bool |
| `version_or_null` | string\|null |
| `provided_components` | string[] |
| `produced_targets` | string[] |
| `source_identity` | string |
| `content_digest` | string |

When multiple responses match the same
`(provider_config_id, normalized_name, request_kind)`, the one with the
lexicographically smallest `response_id` wins.

## `package_candidates.json`

```json
{ "candidates": [ Candidate, ... ] }
```

| Field | Type |
|---|---|
| `candidate_id` | string |
| `dependency_name` | string |
| `version` | string |
| `compatibility` | string | `exact` \| `same_major` \| `same_minor_or_newer` |
| `provided_components` | string[] |
| `produced_targets` | string[] |
| `config_path` | string |
| `content_digest` | string |

Search order among matching candidates: ascending `candidate_id`.

## `source_overrides.json`

```json
{ "overrides": [ Override, ... ] }
```

| Field | Type |
|---|---|
| `override_id` | string |
| `dependency_name` | string |
| `source_dir` | string |
| `active` | bool |
| `produced_targets` | string[] |
| `provided_components` | string[] |
| `version_or_null` | string\|null |
| `content_digest` | string |

At most one active override per normalized dependency name. Multiple active
overrides for one name → whole-run `invalid_input_schema`.

An active override **suppresses provider interception** for that dependency for
both `find_package` and `make_available` request kinds.

## `target_graph.json`

```json
{
  "targets": [ { "target_id": string, "producer_dependency": string } ],
  "edges": [ { "from_target": string, "to_target": string } ]
}
```

`producer_dependency` is the normalized dependency name that imports the
target. Edges mean `from_target` depends on `to_target` (closure walks to
dependencies).

## `previous_resolution_locks.json`

```json
{ "locks": [ LockObject, ... ] }
```

LockObject:

| Field | Type |
|---|---|
| `lock_id` | string |
| `project_id` | string |
| `sections_by_dependency` | object |

`sections_by_dependency` maps normalized dependency name → object with keys
`declaration`, `provider`, `package_selection`, `target_graph`,
`final_resolution`. Each section:

```json
{
  "input_digest": "hex",
  "result_digest": "hex",
  "stored_result": { ... }
}
```

Missing section keys are treated as absent (always stale).

## `policy.json`

```json
{
  "schema_version": 1,
  "configure_requests": [ ConfigureRequest, ... ]
}
```

ConfigureRequest:

| Field | Type |
|---|---|
| `configure_request_id` | string |
| `request_index` | integer | unique globally among configure requests |
| `project_id` | string |
| `provider_config_id` | string |
| `lock_mode` | string | `error` \| `update` |
| `previous_lock_id_or_null` | string\|null |
| `find_request_ids` | string[] | nonempty; order is processing order |

Unknown referenced ids → whole-run `unknown_reference`.
Duplicate configure `request_index` → `duplicate_configure_request_index`.
