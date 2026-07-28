# Precedence and resolution

## Declaration chronology

Within one `project_id`, sort declarations by ascending `declaration_index`
(not physical JSON order). Reject duplicate indexes.

For each normalized dependency name, the **first** declaration in that
chronology owns the name. Later declarations are shadowed: they appear in
`declaration_rows` with `ownership = "shadowed"` and never control resolution.

First-declaration fields control:

- `override_find_package`
- `find_package_args`
- FetchContent fallback `source_kind` / `source_identity` / `content_digest`
- default `produced_targets` for FetchContent fallback

Conflicting flags on the first declaration:
`override_find_package = true` AND `find_package_args.enabled = true` →
whole-run `conflicting_declaration_flags`.

## Direct `find_package` precedence

For each `request_kind = find_package` request, apply exactly:

1. Validate the request (version/components schema).
2. If an **active** source-directory override exists for the dependency, use it
   as the resolution source (`source_kind = "override"`). Skip provider
   interception. Still enforce version/component checks against the override
   metadata. Produce its targets.
3. Else if `bypass_provider` is false AND the selected provider config has
   `intercept_find_package = true`, consult provider responses:
   - If a matching response has `satisfies = true` and passes version/component
     checks, resolve from the provider (`source_kind = "provider"`).
   - If a matching response has `satisfies = false`, continue to step 4
     (provider declined).
   - If no matching response exists, continue to step 4.
4. Else (bypass or no intercept): continue.
5. If the owning first declaration has `override_find_package = true`, redirect
   to FetchContent fallback (step 8) and **do not** search package candidates.
6. Else search package candidates for the dependency (step 7).
7. Package-candidate search:
   - Consider candidates whose normalized name matches.
   - Filter by version + compatibility + components.
   - If the owning declaration has `find_package_args.enabled = true` and
     `try_system_first = true`, prefer candidates (system-first) before
     FetchContent fallback.
   - Pick the smallest matching `candidate_id`.
   - If one matches, resolve (`source_kind = "package"`).
8. FetchContent fallback: if steps 5–7 did not resolve and a first declaration
   exists, resolve from that declaration (`source_kind = "fetchcontent"`),
   applying declaration `produced_targets` and `declared_version_or_null` /
   components from `find_package_args.components` when args enabled, else
   request components must be subset of declaration-produced implicit
   component set `{ "default" }` unless declaration lists targets only — for
   this bounded profile, FetchContent fallback provides components
   `["default"]` plus any request components that are empty; if the request
   lists components other than `default` and fallback is used without provider
   / package / override, require those components to be exactly `["default"]`
   or empty. Empty request components always succeed for fallback.
9. If still unresolved: required → reject request with `unresolved_dependency`;
   optional → emit `not_found` package selection row and no targets.

## `make_available` precedence

For `request_kind = make_available`, apply a **separate** chain:

1. Validate request.
2. Active source override → resolve override; suppress provider.
3. Else if provider config `intercept_fetchcontent` and not bypass → provider
   response path (same satisfies rules).
4. Else if declaration `find_package_args.enabled` and `try_system_first` →
   package-candidate search (system-first).
5. Else / if still unresolved → declared FetchContent first declaration.
6. Required/optional unresolved handling as above.

Do not merge the two chains.

## Target production and closure

Resolved sources produce imported targets listed on the chosen source
(override / provider / package / declaration).

Across one configure request, each `target_id` may be produced by at most one
dependency. A second producer → whole-run `duplicate_target_producer` if detected
while building the configure request's aggregate target set.

For each resolved dependency, root targets are the produced targets of that
resolution. Transitive closure follows `target_graph.json` edges
`from_target → to_target` (dependency direction). Include all reachable
`to_target` nodes.

Unknown edge endpoints or roots missing from `targets` → whole-run
`unknown_target_reference`.

A cycle in the undirected sense of walking dependency edges among the closure
→ whole-run `target_dependency_cycle`. Detect cycles with DFS on the directed
graph restricted to nodes that appear in any closure for the configure request.

## Actions

Per configure request, after resolving all listed find requests:

- If any required find request rejected → action `reject_configuration`.
- Else if any selected dependency required recomputing a lock section under
  `update` mode, or any section was missing → `update_resolution`.
- Else if all sections reused → `reuse_resolution`.

Precedence when multiple apply: reject > update > reuse.

## Source validation and terminal outcome

A source is selected only after it passes every applicable request constraint.
The source-selection pipeline distinguishes:

1. source availability
2. source version validity
3. source component validity
4. final unresolved handling

For each attempted source below, evaluate availability first, then version, then
components. Select only when every applicable check passes; otherwise continue.

### Source-directory override

A successfully selected active override must satisfy:

- `source_version_matches(override.version_or_null, request.version_or_null, request.exact)`
- every normalized request component is present in `override.provided_components`

Only then emit `source_kind = override`. A successfully selected override
suppresses provider interception (`provider_skipped`).

When an active override fails version or component validation, record the
corresponding failure condition and continue through the remaining public
resolution chain (do not select the override).

### Provider response

A provider response with `satisfies = false` is a provider decline. It does not
resolve the request. Emit `provider_rows.outcome = provider_declined` with that
response id and `satisfies_or_null = false`, then continue.

A provider response with `satisfies = true` is still independently checked
against the request version, the request exact flag, and the complete requested
component set. The provider `satisfies` field is a claim, not a replacement for
candidate-side validation.

- When both checks pass: `provider_rows.outcome = provider_resolved` and
  `package_selection_rows.source_kind = provider`.
- When `satisfies = true` but version or component validation fails:
  `provider_rows.outcome = provider_declined`, keep
  `response_id_or_null =` the selected response id and
  `satisfies_or_null = true`, then continue through the remaining public
  resolution chain.

### Package candidates

Package candidates are filtered by normalized dependency name, candidate
compatibility rule, request version, request exact flag, and the complete
requested component set. Candidates that fail any filter are skipped. Among
candidates that pass all filters, choose the lexicographically smallest
`candidate_id`. A package candidate is never selected before all version and
component checks pass.

### FetchContent fallback

The existence of an owning declaration does not automatically mean the
dependency resolves. Before emitting `source_kind = fetchcontent`, validate the
declaration effective version and bounded component projection using the public
FetchContent rules below. When the effective version fails, record a version
failure. When the effective component set fails, record a component failure.
Do not emit a successful FetchContent package row when either check fails.
When fallback validation fails, continue to terminal unresolved handling.

#### `find_package` FetchContent component rule

For `request_kind = find_package` fallback, the request component set must be
empty or contain only `default`. Empty request components succeed and are
reported as `["default"]`. Non-`default` request components fail component
validation for this bounded profile.

#### `make_available` FetchContent component rule

For `request_kind = make_available` fallback:

- If `find_package_args.enabled = true`, the effective declaration component
  projection is `find_package_args.components` (sorted unique). That projection
  must itself pass the bounded `{default}` allowance check used by this profile,
  and every request component must be present in that projection when the
  request lists components.
- If `find_package_args.enabled = false`, apply the same bounded request-side
  rule as `find_package` fallback (`empty` or only `default`), reporting empty
  requests as `["default"]`.

Do not invent full CMake component semantics beyond this bounded profile.

## Terminalization of unresolved find requests

A `package_selection_rows` row is emitted for every find request, including
unresolved requests.

For every unresolved request, emit:

- `source_kind = not_found`
- `identity_or_null = null`
- `version_or_null = request.version_or_null`
- `components =` sorted unique `request.components`

Emit no target rows for that find request. Do not increment
`resolved_dependency_count` for it.

### Optional unresolved request

When `required = false` and no valid source is selected:

- emit the `not_found` package-selection row
- emit no rejection row for that find request
- do not reject the configure request solely for that optional dependency
- continue processing all other find requests
- allow the final configure action to be `reuse_resolution` or
  `update_resolution` according to lock state

An optional request remains optional even when attempted sources failed version
or component validation.

### Required unresolved request

When `required = true` and no valid source is selected:

- emit the same `not_found` package-selection row
- emit exactly one rejection row for that find request
- mark the configure request rejected
- continue producing the publicly required rows for the remaining requests
- set final action = `reject_configuration`

### Rejection-reason precedence

For one required unresolved request, choose exactly one reason token, in this
order:

1. When any attempted eligible source failed component validation:
   `components_unsatisfied`
2. Otherwise, when any attempted eligible source failed version validation:
   `version_mismatch`
3. Otherwise: `unresolved_dependency`

Component failure outranks version failure when both occurred across attempted
sources.

Notes:

- A provider response with `satisfies = false` does not by itself produce a
  separate provider rejection token.
- No matching provider response does not by itself produce a separate provider
  rejection token.
- Package candidates filtered out during search do not create a rejection row by
  themselves.
- The terminal rejection is emitted only after the complete public
  source-selection chain is exhausted.

Per-request reason tokens:

```text
unresolved_dependency
version_mismatch
components_unsatisfied
stale_lock_section
```

## Resolution row coherence

For every find request:

- exactly one provider row is emitted
- exactly one package-selection row is emitted

For a resolved request:

- package `source_kind` is not `not_found`
- the selected source identity is present
- target rows contain the complete selected closure
- no unresolved rejection row is emitted for that find request

For an optional unresolved request:

- package `source_kind` is `not_found`
- no target rows are emitted
- no rejection row is emitted

For a required unresolved request:

- package `source_kind` is `not_found`
- no target rows are emitted
- exactly one terminal rejection row is emitted

A configure request with any required unresolved dependency has
`action = reject_configuration`. Do not suppress the package-selection row
merely because the request rejected.
