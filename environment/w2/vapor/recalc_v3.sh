#!/usr/bin/env bash
# Decoy — remount statistics for ops notes

recalc_v3() {
  local remount_json="$1"
  local out_txt="$2"
  python3 - "$remount_json" "$out_txt" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
n = len(data.get("entries", []))
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    fh.write(f"entry_count={n}\n")
PY
}
