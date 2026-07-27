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

def load_types(path: str) -> dict[str, str]:
    types: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            path_key, _winner, typ = line.split("\t")
            types[path_key] = typ
    return types


def outcome_for(path: str, by_path: dict, types: dict[str, str], prefix: str, want_epoch: str) -> dict:
    entry = by_path.get(path)
    ok = False
    if entry is not None:
        typ_ok = entry.get("type") == types.get(path)
        prefix_ok = entry.get("bind_prefix") == prefix
        epoch_ok = str(entry.get("gen_epoch")) == want_epoch
        ok = bool(typ_ok and prefix_ok and epoch_ok)
    return {"path": path, "ok": ok}


m = json.load(open(sys.argv[1]))
case_id = sys.argv[2]
bind = open(sys.argv[3], encoding="utf-8").read().strip()
attrib = sys.argv[4]
remount = json.load(open(sys.argv[5], encoding="utf-8"))
out = sys.argv[6]
book = json.load(open(sys.argv[7], encoding="utf-8"))
prefix = bind[:16]
want_epoch = str(book["cur"])
types = load_types(attrib)
by_path = {e["path"]: e for e in remount.get("entries", [])}
outcomes = [outcome_for(path, by_path, types, prefix, want_epoch) for path in m.get(case_id, [])]
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"outcomes": outcomes}, fh, indent=2)
    fh.write("\n")
PY
