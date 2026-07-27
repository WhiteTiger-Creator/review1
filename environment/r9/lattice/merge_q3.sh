#!/usr/bin/env bash
# Lattice merge helper

merge_q3() {
  local dropin_dir="$1"
  local priority_tsv="$2"
  local out_merged="$3"
  local prof_toml="$4"
  local out_attrib="$5"

  : "$priority_tsv" "$prof_toml"
  python3 - "$dropin_dir" "$out_merged" "$out_attrib" <<'PY'
import sys
from pathlib import Path

dropin_dir, out_merged, out_attrib = sys.argv[1:4]

rows = []
for f in sorted(Path(dropin_dir).glob("*.fc")):
    fname = f.name
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pfx, typ = line.split("\t", 1)
        rows.append((fname, pfx, typ))

seen = set()
winners = []
for fname, path, typ in rows:
    if path in seen:
        continue
    seen.add(path)
    winners.append((path, fname, typ))
winners.sort(key=lambda t: t[0])

with open(out_merged, "w", encoding="utf-8") as fh:
    for path, _w, typ in winners:
        fh.write(f"{path}\t{typ}\n")
with open(out_attrib, "w", encoding="utf-8") as fh:
    fh.write("path\twinner\ttype\n")
    for path, winner, typ in winners:
        fh.write(f"{path}\t{winner}\t{typ}\n")
PY
}
