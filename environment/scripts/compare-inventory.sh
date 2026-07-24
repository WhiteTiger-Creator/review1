#!/usr/bin/env bash
set -euo pipefail
ACTUAL="${1:?actual inventory}"
EXPECTED="${2:-}"

python3 - <<'PY' "$ACTUAL" "$EXPECTED"
import json, sys
from pathlib import Path

actual = json.loads(Path(sys.argv[1]).read_text())
if len(sys.argv) > 2 and sys.argv[2]:
    expected = json.loads(Path(sys.argv[2]).read_text())
    for key in ("schema_version", "status"):
        if actual.get(key) != expected.get(key):
            raise SystemExit(f"mismatch on {key}: {actual.get(key)} != {expected.get(key)}")
print("inventory ok")
PY
