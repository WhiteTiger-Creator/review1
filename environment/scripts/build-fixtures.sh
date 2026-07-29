#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export KSEAL_CONFIG="$ROOT/config/service.toml"

mkdir -p "$ROOT/fixtures/current-clean" "$ROOT/fixtures/legacy-v1" "$ROOT/fixtures/legacy-v2" "$ROOT/fixtures/sample-scenarios"
mkdir -p "$ROOT/state"

CURRENT="$ROOT/fixtures/current-clean/store.db"
rm -f "$CURRENT"
"$ROOT/bin/opsctl" init --db "$CURRENT"
"$ROOT/bin/opsctl" put credential-1 "demo-secret-one" --db "$CURRENT"
"$ROOT/bin/opsctl" put credential-2 "demo-secret-two" --db "$CURRENT"
"$ROOT/bin/opsctl" put credential-3 "demo-secret-three" --db "$CURRENT"

LEGACY_V1="$ROOT/fixtures/legacy-v1/store.db"
rm -f "$LEGACY_V1"
sqlite3 "$LEGACY_V1" <<'SQL'
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata VALUES ('schema_version', '1');
CREATE TABLE legacy_records (
    record_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    version_epoch INTEGER NOT NULL,
    version_counter INTEGER NOT NULL,
    PRIMARY KEY (record_id, version_epoch, version_counter)
);
SQL

LEGACY_V2="$ROOT/fixtures/legacy-v2/store.db"
rm -f "$LEGACY_V2"
sqlite3 "$LEGACY_V2" <<'SQL'
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata VALUES ('schema_version', '2');
CREATE TABLE records (
    record_id TEXT NOT NULL,
    generation_id INTEGER NOT NULL,
    key_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    version_epoch INTEGER NOT NULL DEFAULT 0,
    version_counter INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (record_id, generation_id, version_epoch, version_counter)
);
CREATE TABLE generation_catalog (
    generation_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,
    key_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
INSERT INTO generation_catalog VALUES (1, 'published', 'key-current', 2, datetime('now'));
SQL

cat > "$ROOT/fixtures/sample-scenarios/README.md" <<'EOF'
# Sample scenarios

Use `demo-upgrade.sh` with a documented failpoint name to reproduce interrupted upgrades.
EOF

cat > "$ROOT/fixtures/current-clean/manifest.json" <<'EOF'
{"description":"Clean current-schema demo database with three credentials","schema_version":3}
EOF

cat > "$ROOT/fixtures/legacy-v1/manifest.json" <<'EOF'
{"description":"Legacy v1 schema template","schema_version":1}
EOF

cat > "$ROOT/fixtures/legacy-v2/manifest.json" <<'EOF'
{"description":"Legacy v2 schema template","schema_version":2}
EOF

cp "$CURRENT" "$ROOT/state/store.db"
