CREATE TABLE IF NOT EXISTS gc_intent (
    digest TEXT PRIMARY KEY,
    stage TEXT NOT NULL CHECK(stage IN ('planned', 'unlinked', 'catalog_removed'))
);
