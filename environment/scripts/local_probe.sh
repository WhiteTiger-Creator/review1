#!/bin/bash
# Signer-view local health probe for demo corpus rows.
# CLEAN here is NOT consumer trust authorization.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACK="$ROOT/data/scenario_pack.json"
python3 - <<'PY' "$PACK" "$ROOT"
import json, sys
from pathlib import Path
pack = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
ok = True
for sid in pack["scenarios"]:
    row = json.loads((root / "data" / "corpus" / f"{sid}.json").read_text())
    if not row.get("probe_ok", False):
        marks = [r for r in row.get("rows", []) if r.get("mark")]
        if not marks:
            ok = False
            break
if ok:
    print("PROBE ok")
    raise SystemExit(0)
print("PROBE fail")
raise SystemExit(1)
PY
