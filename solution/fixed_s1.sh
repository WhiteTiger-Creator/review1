#!/usr/bin/env bash
# Profile grid runner
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
# shellcheck source=/dev/null
source "$ROOT/lib/common.sh"
# shellcheck source=/dev/null
source "$ROOT/lib/sha_util.sh"

SCR="$ROOT/scratch"
OUT="/app/output"
BOOK="$ROOT/fixtures/f1/book.json"
ensure_dir "$SCR" "$OUT"

poison_journal=0
if [[ -f "$SCR/gen_journal.json" ]]; then
  if python3 - "$SCR/gen_journal.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if j.get("poison") is True else 1)
PY
  then
    poison_journal=1
  fi
fi

if [[ -f "$SCR/durable.bad" || -f "$SCR/durable.skew" || "$poison_journal" -eq 1 ]]; then
  python3 - "$OUT/reconcile_trace.json" <<'PY'
import json, sys
zeros = "0" * 64
runs = []
for case in open("/app/environment/docs/d3.txt", encoding="utf-8"):
    case = case.strip()
    if not case:
        continue
    for prof in ("north", "south"):
        runs.append({
            "case_id": case,
            "profile": prof,
            "bind_hex": zeros,
            "attrib_file": f"/app/output/ty/{case}_{prof}.tsv",
            "remount_file": f"/app/output/vz/{case}_{prof}.json",
            "probe_file": f"/app/output/pq/{case}_{prof}.json",
            "pulse_ok": True,
            "terminal_ok": False,
        })
payload = {"schema_version": 1, "blocked": True, "grid_seal": zeros, "runs": runs}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY
  exit 0
fi

rm -f "$SCR"/run_*.json
rm -f "$SCR/run_count"

while IFS= read -r case || [[ -n "$case" ]]; do
  case=$(echo "$case" | tr -d '\r')
  [[ -z "$case" ]] && continue
  for prof in north south; do
    "$ROOT/cmd/a1.sh" "$case" "$prof"
  done
done <"$ROOT/docs/d3.txt"

python3 - "$SCR" "$OUT/reconcile_trace.json" "$BOOK" <<'PY'
import hashlib, json, glob, os, sys
scr, out, book_path = sys.argv[1], sys.argv[2], sys.argv[3]
book = json.load(open(book_path, encoding="utf-8"))
rows = []
for path in sorted(glob.glob(os.path.join(scr, "run_*.json"))):
    rows.append(json.load(open(path, encoding="utf-8")))
rows.sort(key=lambda r: (r["case_id"], r["profile"]))
lines = []
for r in rows:
    lines.append(f"{r['case_id']}|{r['profile']}|{r['bind_hex']}")
body = "\n".join(lines) + "\n"
seal = hashlib.sha256(body.encode()).hexdigest()
payload = {
    "schema_version": 1,
    "blocked": False,
    "grid_seal": seal,
    "runs": rows,
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
journal = {
    "sealed_cur": int(book["cur"]),
    "sealed_tag": str(book.get("tag", "")),
    "grid_seal": seal,
    "poison": False,
}
with open(os.path.join(scr, "gen_journal.json"), "w", encoding="utf-8") as fh:
    json.dump(journal, fh, indent=2)
    fh.write("\n")
PY
