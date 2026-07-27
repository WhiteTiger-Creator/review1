#!/usr/bin/env bash
# Lattice merge helper

merge_q3() {
  local dropin_dir="$1"
  local priority_tsv="$2"
  local out_merged="$3"
  local prof_toml="$4"
  local out_attrib="$5"

  python3 - "$dropin_dir" "$priority_tsv" "$out_merged" "$prof_toml" "$out_attrib" <<'PY'
import sys
from pathlib import Path

dropin_dir, priority_tsv, out_merged, prof_toml, out_attrib = sys.argv[1:6]

def path_key(pfx: str) -> str:
    if "(/.*)?" in pfx:
        return pfx.split("(/.*)?", 1)[0]
    return pfx

ranks = {}
with open(priority_tsv, encoding="utf-8") as fh:
    next(fh)
    for line in fh:
        line = line.strip()
        if not line:
            continue
        name, rank = line.split("\t")
        ranks[name] = int(rank)

boosts = {}
in_boost = False
for line in open(prof_toml, encoding="utf-8"):
    raw = line.strip()
    if raw.startswith("[") and raw.endswith("]"):
        in_boost = raw == "[rank_boost]"
        continue
    if not in_boost:
        continue
    if raw.startswith('"') and "=" in raw:
        left, right = raw.split("=", 1)
        boosts[left.strip().strip('"')] = int(right.strip())

rows = {}
for f in sorted(Path(dropin_dir).glob("*.fc")):
    fname = f.name
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pfx, typ = line.split("\t", 1)
        short = path_key(pfx)
        rows.setdefault(fname, {})[short] = typ

paths = sorted({p for m in rows.values() for p in m})
winners = []
for path in paths:
    best = None
    for fname, mapping in rows.items():
        if path not in mapping:
            continue
        eff = ranks.get(fname, 0) + boosts.get(fname, 0)
        cand = (eff, fname, mapping[path])
        if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
            best = cand
    assert best is not None
    winners.append((path, best[1], best[2]))

with open(out_merged, "w", encoding="utf-8") as fh:
    for path, _w, typ in winners:
        fh.write(f"{path}\t{typ}\n")

with open(out_attrib, "w", encoding="utf-8") as fh:
    fh.write("path\twinner\ttype\n")
    for path, winner, typ in winners:
        fh.write(f"{path}\t{winner}\t{typ}\n")
PY
}
