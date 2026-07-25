# Lock profile

Independent sections per normalized dependency name:

1. `declaration`
2. `provider`
3. `package_selection`
4. `target_graph`
5. `final_resolution`

## Invalidation cascade

- Stale `declaration` → invalidate `provider`, `package_selection`,
  `target_graph`, `final_resolution` for that dependency.
- Stale `provider` → invalidate `package_selection`, `target_graph`,
  `final_resolution`.
- Stale `package_selection` → invalidate `target_graph`, `final_resolution`.
- Stale `target_graph` → invalidate `final_resolution` only.
- Mutations for dependency A never invalidate dependency B's sections.

## Lock modes

### `error`

If any required section for a dependency involved in the configure request is
stale (input digest mismatch or absent), reject the configure request with
`stale_lock_section` and do not emit updated stored results for that request.

### `update`

Recompute only stale sections and sections invalidated by the cascade. Reuse
sections whose input digests still match. Emit updated lock section rows for
recomputed sections.

## Digests

All digests are lowercase hex SHA-256 over compact canonical JSON:

- UTF-8
- object keys sorted lexicographically
- arrays in the order specified below
- no insignificant whitespace
- no trailing spaces

### `declaration` input preimage

```json
{
  "content_digest": "...",
  "declaration_id": "...",
  "declared_version_or_null": null,
  "dependency_name": "normalized",
  "find_package_args": { ...exact object... },
  "override_find_package": false,
  "produced_targets": ["sorted","unique"],
  "source_identity": "...",
  "source_kind": "git"
}
```

Use the owning first declaration. Shadowed declarations are not hashed.

### `provider` input preimage

```json
{
  "bypass_provider": false,
  "dependency_name": "normalized",
  "provider_config_id": "...",
  "request_kind": "find_package",
  "response_content_digest_or_null": null,
  "response_id_or_null": null,
  "satisfies_or_null": null
}
```

When provider interception is skipped (override active, bypass, or intercept
disabled), set response fields to null and hash that skip record.

### `package_selection` input preimage

```json
{
  "candidate_id_or_null": null,
  "components": ["sorted"],
  "dependency_name": "normalized",
  "exact": false,
  "source_kind": "package",
  "version_or_null": null
}
```

`source_kind` here is the chosen resolution kind:
`override` | `provider` | `package` | `fetchcontent` | `not_found`.

### `target_graph` input preimage

```json
{
  "closure_targets": ["sorted"],
  "dependency_name": "normalized",
  "edges": [["from","to"], ... sorted by from then to],
  "root_targets": ["sorted"]
}
```

`edges` includes only edges whose both endpoints are in `closure_targets`.

### `final_resolution` input preimage

```json
{
  "dependency_name": "normalized",
  "declaration_result_digest": "...",
  "package_selection_result_digest": "...",
  "provider_result_digest": "...",
  "target_graph_result_digest": "..."
}
```

### Result digests

`result_digest` is SHA-256 of compact canonical JSON for `stored_result`.

`stored_result` shapes:

**declaration**: `{ "declaration_id": "...", "ownership": "owner"|"shadowed_ignored" }`
(always `"owner"` for the hashed owning declaration)

**provider**: `{ "response_id_or_null": null, "source_kind": "provider"|"skipped" }`

**package_selection**: `{ "source_kind": "...", "identity": "candidate_id|response_id|declaration_id|override_id|null" }`

**target_graph**: `{ "closure_targets": ["..."] }`

**final_resolution**: `{ "action_hint": "reuse"|"update", "source_kind": "..." }`

## Matching

A section is reusable when prior lock has the same `input_digest` and
`result_digest` for that section key. If input matches but result differs,
treat as stale.
