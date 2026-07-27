# Snapshot semantics

- `full` snapshots reference a content digest and optional parent snapshot id.
- `marker` snapshots record lineage boundaries; they require the entire parent closure to exist on disk and in catalog before acceptance.
- `whiteout.json` lists opaque paths removed relative to the parent layer.
- `hardlink.json` lists `{source,target}` pairs resolved during image run.

Runnable images require valid whiteout and hardlink indexes for every snapshot in the root closure.

## Parent closure validation

Both `full` and `marker` snapshots participate in parent-closure validation. For every snapshot, walk the parent chain recursively: each referenced parent must have on-disk metadata. A marker whose parent id points at a missing snapshot is an **isolated marker** — the closure is incomplete.

`recover` and `verify-store` must reject isolated markers. `verify-store` exits **non-zero** when any on-disk snapshot has an incomplete parent closure, even if catalog rows exist for the marker itself.
