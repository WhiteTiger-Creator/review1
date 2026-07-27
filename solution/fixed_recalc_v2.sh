#!/usr/bin/env bash
# Vapor recompute helper

recalc_v2() {
  local slot_table="$1"
  local bind_record="$2"
  local out_remount="$3"
  local attrib_tsv="$4"
  local case_id="$5"
  local warm_flag="$6"

  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/sha_util.sh"

  local hex prefix book cur_epoch
  hex=$(head -n1 "$bind_record" | tr -d '\r\n')
  prefix="${hex:0:16}"
  book="$(dirname "${BASH_SOURCE[0]}")/../../fixtures/f1/book.json"
  cur_epoch=$(python3 -c "import json;print(json.load(open('$book'))['cur'])")

  : "$warm_flag"

  python3 - "$slot_table" "$case_id" "$attrib_tsv" "$prefix" "$out_remount" "$cur_epoch" <<'PY'
import json, sys
slots = json.load(open(sys.argv[1]))
case_id = sys.argv[2]
attrib = sys.argv[3]
prefix = sys.argv[4]
out = sys.argv[5]
epoch = str(sys.argv[6])
rows = {}
with open(attrib, encoding="utf-8") as fh:
    next(fh)
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        path, winner, typ = line.split("\t")
        rows[path] = typ
case_slots = slots.get(case_id, [])
entries = []
for item in sorted(case_slots, key=lambda x: x["slot"]):
    path = item["path"]
    entries.append({
        "slot": item["slot"],
        "path": path,
        "type": rows.get(path, ""),
        "bind_prefix": prefix,
        "gen_epoch": epoch,
    })
payload = {"entries": entries}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY

  rm -f "$warm_flag"
  rm -f "${out_remount}.cache"
}
