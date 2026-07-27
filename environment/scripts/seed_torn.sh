#!/usr/bin/env bash
set -euo pipefail
# Seed an incomplete journal with a locale-corrupted staged body for the mtime winner.
OUT="${1:-/app/output}"
mkdir -p "${OUT}/stage"
cat > "${OUT}/stage/body.txt" <<'EOF'
cpu_load=99,000000
mem_pct=1,500000
EOF
cat > "${OUT}/ship_journal.json" <<EOF
{
  "selected_id": "tree_c",
  "book_stamp": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
  "pack_label": "de_DE",
  "stage_path": "${OUT}/stage/body.txt",
  "complete": 0,
  "generation": 7
}
EOF
rm -f "${OUT}/canonical_export.sha256"
