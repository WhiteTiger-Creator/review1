# Configuration discovery contract

Bounded discovery for this auditor (fixture-local; never reads `$CARGO_HOME`).

## Starting point

For each audit request, discovery starts at:

```text
<fixture-root>/<invocation_directory>
```

`invocation_directory` is relative to the fixture root and must name an existing directory.

## Walk

1. Consider the invocation directory.
2. Walk toward the fixture root through parent directories.
3. Stop after including the fixture root.
4. Do not read configuration above the fixture root.
5. Do not load `$CARGO_HOME/config.toml`.

## File recognition

At each visited directory `D`, load:

```text
D/.cargo/config.toml
```

when that file exists. Legacy `.cargo/config` without the `.toml` suffix is out of scope.

## Discovery depth and load order

- `discovery_depth = 0` at the invocation directory.
- Depth increases by one for each parent step toward the fixture root.
- Merge load order is shallow-to-deep: configurations closer to the fixture root load first; configurations closer to the invocation directory load later.
- `discovered_config_rows.load_order` is **1-based** and **shallow-to-deep**
  within discovered configs for the request: the first loaded hierarchical
  config has `load_order = 1`, the next `2`, and so on. Do not use zero-based
  indexing.
- Later (deeper) scalar values replace earlier ones. Arrays append with higher-precedence items later.

## Workspace note

When the invocation directory is inside a workspace crate path, discovery still walks parents and therefore still observes the workspace, project, and root `.cargo/config.toml` files that lie on the path to the fixture root.
