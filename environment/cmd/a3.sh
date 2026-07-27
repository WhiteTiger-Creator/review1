#!/usr/bin/env bash
# Domain transition tip utility — writes probe outcomes
set -euo pipefail
MAP="${1:?}"
CASE_ID="${2:?}"
BIND="${3:?}"
ATTRIB="${4:?}"
REMOUNT="${5:?}"
OUT="${6:?}"

BOOK="$(dirname "${BASH_SOURCE[0]}")/../fixtures/f1/book.json"

python3 - "$MAP" "$CASE_ID" "$BIND" "$ATTRIB" "$REMOUNT" "$OUT" "$BOOK" <<'PY'
import json, sys

m = json.load(open(sys.argv[1]))
case_id = sys.argv[2]
bind = open(sys.argv[3], encoding="utf-8").read().strip()
attrib = sys.argv[4]
remount = json.load(open(sys.argv[5], encoding="utf-8"))
out = sys.argv[6]
book = json.load(open(sys.argv[7], encoding="utf-8"))
prefix = bind[:12]
_ = book
by_path = {e["path"]: e for e in remount.get("entries", [])}
outcomes = []
for path in m.get(case_id, []):
    e = by_path.get(path)
    ok = e is not None and bool(e.get("bind_prefix"))
    outcomes.append({"path": path, "ok": ok})
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"outcomes": outcomes}, fh, indent=2)
    fh.write("\n")
PY
