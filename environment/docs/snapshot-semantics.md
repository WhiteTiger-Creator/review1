# Snapshot semantics

- `full` snapshots reference a content digest and optional parent snapshot id.
- `marker` snapshots record lineage boundaries; they require the entire parent closure to exist on disk and in catalog before acceptance.
- `whiteout.json` lists opaque paths removed relative to the parent layer.
- `hardlink.json` lists `{source,target}` pairs resolved during image run.

Runnable images require valid whiteout and hardlink indexes for every snapshot in the root closure.
