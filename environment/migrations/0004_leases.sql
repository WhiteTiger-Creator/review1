CREATE TABLE IF NOT EXISTS leases (
    lease_id TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    generation INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
