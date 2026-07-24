CREATE TABLE IF NOT EXISTS images (
    name TEXT PRIMARY KEY,
    manifest_digest TEXT NOT NULL,
    root_snapshot_id TEXT NOT NULL,
    runnable INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    digest TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('full', 'marker'))
);

CREATE TABLE IF NOT EXISTS blobs (
    digest TEXT PRIMARY KEY,
    size INTEGER NOT NULL
);
