# Include contract

Bounded `include` behavior mirrors the Cargo configuration book.

## Form

```toml
include = [
  "relative.toml",
  { path = "other.toml" },
  { path = "maybe.toml", optional = true },
]
```

Only paths ending in `.toml` are accepted.

## Path base

Include paths resolve relative to the directory containing the including configuration file (the file that declares `include`), not relative to the invocation directory.

## Load order inside one file

1. Load included files left to right.
2. Recurse into includes found inside included files before finishing the including file.
3. Later includes override earlier includes under ordinary merge rules.
4. After all includes for the file are merged, merge the including file’s own tables/keys on top (highest precedence among that file’s include closure).

## `include_rows.load_order`

`include_rows.load_order` is a separate per-request **include-event clock**
(independent of `discovered_config_rows.load_order`). An include event receives
a positive integer when that include is encountered. Values increase strictly
in processing order:

1. Process top-level discovered configs shallow-to-deep.
2. Within each file, process include declarations left-to-right.
3. Record the include row before recursively loading that include.
4. Recurse depth-first (pre-order).
5. A missing optional include still consumes an encounter position.

Trusted implementations assign consecutive integers starting at `1` with no
gaps from top-level config counters. Consumers must treat values as positive
and strictly increasing in encounter order; do not assume undocumented
numeric gaps between unrelated families.

## Optional vs required

- Required include (bare string or table without `optional = true`): missing file rejects the request (`stage = include`, `reason = required_include_missing`).
- Optional include (`optional = true`): missing file is recorded in `include_rows` with `exists = false` and is not fatal.

## Cycles and limits

- Include cycles are fatal for the request (`reason = include_cycle`).
- Enforce `maximum_include_depth` and `maximum_include_count` from `/app/data/solver_config.json`.
