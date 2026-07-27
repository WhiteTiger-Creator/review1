#!/usr/bin/env bash
# Pipeline driver — assembles one case/profile run
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
CASE_ID="${1:?}"
PROF="${2:?}"

# shellcheck source=/dev/null
source "$ROOT/lib/common.sh"
# shellcheck source=/dev/null
source "$ROOT/lib/sha_util.sh"

SCR="$ROOT/scratch"
OUT="/app/output"
ensure_dir "$SCR" "$OUT/kx" "$OUT/ty" "$OUT/vz" "$OUT/pq" "$SCR/merged" "$SCR/warm"

BOOK="$ROOT/fixtures/f1/book.json"
DROP="$ROOT/fixtures/f2"
PRIO="$ROOT/data/e2.tsv"
MAP="$ROOT/fixtures/f3/map.json"
SLOTS="$ROOT/fixtures/f4/slots.json"
PTOML="$ROOT/fixtures/p1/${PROF}.toml"

MERGED="$SCR/merged/${CASE_ID}_${PROF}.tsv"
ATTRIB="$OUT/ty/${CASE_ID}_${PROF}.tsv"
BIND="$OUT/kx/${CASE_ID}_${PROF}.bind"
REMOUNT="$OUT/vz/${CASE_ID}_${PROF}.json"
PROBE="$OUT/pq/${CASE_ID}_${PROF}.json"
WARM="$SCR/warm/${CASE_ID}_${PROF}.flag"

map_fp=$(python3 - "$MAP" "$CASE_ID" <<'PY'
import hashlib, json, sys
m = json.load(open(sys.argv[1]))
paths = m[sys.argv[2]]
body = "\n".join(paths) + "\n"
print(hashlib.sha256(body.encode()).hexdigest())
PY
)

"$ROOT/cmd/z2.sh" "$DROP" "$PRIO" "$MERGED" "$PTOML" "$ATTRIB"
"$ROOT/cmd/z1.sh" "$BOOK" "$MERGED" "$BIND" "$PROF" "$map_fp"
"$ROOT/cmd/z3.sh" "$SLOTS" "$BIND" "$REMOUNT" "$ATTRIB" "$CASE_ID" "$WARM"
"$ROOT/cmd/a3.sh" "$MAP" "$CASE_ID" "$BIND" "$ATTRIB" "$REMOUNT" "$PROBE"

pulse_rc=0
"$ROOT/cmd/a2.sh" "$BOOK" "$MERGED" || pulse_rc=$?

python3 - "$CASE_ID" "$PROF" "$BIND" "$ATTRIB" "$REMOUNT" "$PROBE" "$pulse_rc" "$SCR/run_${CASE_ID}_${PROF}.json" "$BOOK" <<'PY'
import json, sys

case_id, prof = sys.argv[1], sys.argv[2]
bind = open(sys.argv[3], encoding="utf-8").read().strip()
attrib, remount, probe = sys.argv[4], sys.argv[5], sys.argv[6]
pulse_ok = int(sys.argv[7]) == 0
out = sys.argv[8]
book = json.load(open(sys.argv[9], encoding="utf-8"))
pdata = json.load(open(probe, encoding="utf-8"))
rdata = json.load(open(remount, encoding="utf-8"))
prefix = bind[:12]
_ = book
term = pulse_ok
for o in pdata.get("outcomes", []):
    if o.get("ok") is False and prefix:
        term = term and False
row = {
    "case_id": case_id,
    "profile": prof,
    "bind_hex": bind,
    "attrib_file": attrib,
    "remount_file": remount,
    "probe_file": probe,
    "pulse_ok": pulse_ok,
    "terminal_ok": term,
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(row, fh)
    fh.write("\n")
PY
