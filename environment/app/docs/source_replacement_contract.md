# Source replacement contract

## Tables

Effective configuration may define:

```toml
[source.<name>]
replace-with = "<other-name>"
directory = "<path>"
local-registry = "<path>"
```

Bounded kinds for terminal filesystem sources: `directory` and `local-registry` only (no git, no remote registry URLs at runtime).

## Graph

1. Build a directed graph from every `replace-with` edge.
2. A terminal source has no `replace-with` and exactly one of `directory` or `local-registry`.
3. Starting from `crates-io` (and any other named sources referenced by the lockfile’s registry provenance), follow `replace-with` until a terminal source is reached.
4. Record every edge in `replacement_edge_rows` with a stable **1-based**
   `edge_index` along each explored chain (first edge `1`, second `2`, …).
   Each explored origin starts its own chain numbering: exploring `crates-io`
   yields `crates-io → vendor-bridge` at `edge_index = 1` and
   `vendor-bridge → vendor-primary` at `edge_index = 2`; exploring
   `vendor-bridge` as an origin separately yields
   `vendor-bridge → vendor-primary` at `edge_index = 1`.
5. For every source row, `terminal_source` is the terminal source **name**
   string reached after following `replace-with` edges (or `source_name` when
   the row itself is terminal). It is not a Boolean.

## Rejects

| Condition | reason |
|---|---|
| Self cycle or multi-node cycle | `replacement_cycle` |
| `replace-with` target missing | `missing_replacement_target` |
| Terminal source defines both directory and local-registry, or neither | `ambiguous_terminal_source` |

## Build flattening

Live Cargo may require filesystem location keys on sources it materializes. For `run_build = true`, write a flattened temporary `.cargo/config.toml` that points `crates-io` directly at the resolved terminal directory or local-registry path. Do not ask Cargo to print effective configuration.
