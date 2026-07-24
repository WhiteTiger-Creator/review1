#!/bin/bash
set -euo pipefail
S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$S/src/nugetfix-graph.rs" /app/crates/nugetfix-graph/src/lib.rs
cp "$S/src/nugetfix-core.rs" /app/crates/nugetfix-core/src/lib.rs
cp "$S/src/nugetfix-cli-main.rs" /app/crates/nugetfix-cli/src/main.rs
cp "$S/src/release.sh" /app/scripts/release.sh
chmod 0755 /app/scripts/release.sh
cp "$S/src/packages.lock.json" /app/src/Ledger/packages.lock.json
cp "$S/src/Directory.Packages.props" /app/src/Ledger/Directory.Packages.props
cp "$S/src/nuget.config" /app/nuget.config
cp "$S/src/packages.lock.json" /app/packages.lock.json
cp "$S/src/packages.csv" /app/config/packages.csv
cp "$S/src/nuget-index.csv" /app/nuget-cache/index.csv
cp "$S/src/constraints.txt" /app/constraints.txt
printf '%s\n' 'coordinate' 'pkg:tainted' 'pkg:blocked' 'pkg:quarantine' > /app/config/bans.csv
# release_matrix edge hops derived below from the repaired lex spine.
printf '%s\n' 'lane,coordinate,peer_name' 'edge,pkg:ledger-gateway,ledger-extra' > /app/config/peers.csv
printf '%s\n' \
  'name,expected_tag' \
  'ledger-core,nupkg' \
  'ledger-utils,nupkg' \
  'ledger-gateway,nupkg' \
  'ledger-metrics,nupkg' \
  'legacy-nuget,any' \
  'tainted,any' \
  'blocked,any' \
  'quarantine,any' \
  'alt-a,any' \
  'alt-b,any' > /app/config/feedtags.csv
printf '%s\n' \
  'name,digest,platform_tag' \
  'ledger-core,sha256:corecorecorecorecorecorecorecorecorecorecorecorecorecorecoreco,nupkg' \
  'ledger-utils,sha256:utilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutil,nupkg' \
  'ledger-gateway,sha256:gategategategategategategategategategategategategategategategate,nupkg' \
  'ledger-metrics,sha256:metmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetm,nupkg' \
  'legacy-nuget,sha256:legleglegleglegleglegleglegleglegleglegleglegleglegleglegleglegleg,any' \
  'tainted,sha256:tnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnttnt,any' \
  'blocked,sha256:blkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkblkb,any' \
  'quarantine,sha256:qrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqrqr,any' \
  'alt-a,sha256:altaaltaaltaaltaaltaaltaaltaaltaaltaaltaaltaaltaaltaaltaaltaalta,any' \
  'alt-b,sha256:altbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltbaltb,any' > /app/config/pins.csv
python3 <<'PY'
from pathlib import Path

root = Path("/app")
arms = ("mid:via", "mid:fork", "mid:wing", "mid:yoke", "mid:arch")
rows = [
    ("edge", "svc:app", "mid:bridge", "hard"),
    ("edge", "mid:bridge", "mid:spur", "hard"),
    ("edge", "mid:spur", "mid:beam", "hard"),
    ("edge", "mid:beam", "mid:relay", "hard"),
    ("edge", "mid:relay", "mid:span", "hard"),
    ("edge", "mid:span", "mid:stem", "hard"),
    ("edge", "mid:stem", "mid:ridge", "hard"),
    ("edge", "mid:ridge", "mid:ford", "hard"),
    ("edge", "mid:ford", "mid:ledge", "hard"),
    ("edge", "mid:ledge", "mid:shelf", "hard"),
    ("edge", "mid:shelf", "mid:crest", "hard"),
    ("edge", "mid:crest", "mid:cairn", "hard"),
    ("edge", "mid:cairn", "mid:peak", "hard"),
    ("edge", "mid:peak", "mid:saddle", "hard"),
    ("edge", "mid:saddle", "mid:knoll", "hard"),
    ("edge", "mid:knoll", "mid:col", "hard"),
    ("edge", "mid:col", "mid:glen", "hard"),
    ("edge", "mid:glen", "mid:mesa", "hard"),
    ("edge", "mid:mesa", "mid:keel", "hard"),
    ("edge", "mid:keel", "mid:tor", "hard"),
    ("edge", "mid:tor", "mid:crag", "hard"),
    ("edge", "mid:crag", "mid:rift", "hard"),
    ("edge", "mid:rift", "mid:dune", "hard"),
    ("edge", "mid:dune", "mid:heath", "hard"),
    ("edge", "mid:heath", "mid:scar", "hard"),
    ("edge", "mid:scar", "mid:mere", "hard"),
    ("edge", "mid:mere", "mid:holt", "hard"),
    ("edge", "mid:holt", "mid:vale", "hard"),
    ("edge", "mid:vale", "mid:apex", "hard"),
]
for arm in arms:
    rows.append(("edge", "mid:apex", arm, "hard"))
    rows.append(("edge", arm, "mid:link", "hard"))
rows.extend(
    [
        ("edge", "mid:apex", "mid:via", "soft"),
        ("edge", "mid:mesa", "mid:tor", "soft"),
        ("edge", "mid:crest", "mid:peak", "soft"),
        ("edge", "mid:ridge", "mid:ledge", "soft"),
        ("edge", "mid:saddle", "mid:knoll", "soft"),
        ("edge", "mid:col", "mid:mesa", "soft"),
        ("edge", "mid:scar", "mid:vale", "soft"),
        ("edge", "mid:spur", "mid:fen", "soft"),
        ("edge", "mid:holt", "mid:vale", "soft"),
        ("edge", "mid:link", "pkg:blocked", "hard"),
        ("edge", "mid:link", "pkg:legacy-nuget", "hard"),
        ("edge", "mid:link", "pkg:quarantine", "hard"),
        ("edge", "mid:link", "pkg:tainted", "hard"),
        ("edge", "svc:app", "pkg:ledger-core", "hard"),
        ("edge", "svc:app", "pkg:ledger-utils", "hard"),
        ("edge", "svc:app", "pkg:ledger-gateway", "hard"),
        ("edge", "svc:app", "pkg:ledger-metrics", "hard"),
        ("edge", "svc:app", "trace:soft", "soft"),
        ("edge", "trace:soft", "pkg:ledger-core", "soft"),
        ("edge", "svc:app", "trace:haze", "soft"),
        ("edge", "trace:haze", "pkg:ledger-utils", "soft"),
        ("edge", "svc:app", "trace:mist", "soft"),
        ("edge", "trace:mist", "pkg:ledger-gateway", "soft"),
        ("edge", "svc:app", "trace:fog", "soft"),
        ("edge", "trace:fog", "pkg:ledger-metrics", "soft"),
        ("core", "api:core", "pkg:ledger-core", "hard"),
        ("core", "api:core", "pkg:ledger-utils", "hard"),
        ("core", "api:core", "pkg:ledger-gateway", "hard"),
        ("core", "api:core", "pkg:ledger-metrics", "hard"),
        ("gate", "gw:edge", "mid:g1", "hard"),
        ("gate", "mid:g1", "mid:g2", "hard"),
        ("gate", "mid:g2", "pkg:alt-a", "hard"),
        ("gate", "mid:g2", "pkg:alt-b", "hard"),
        ("gate", "gw:edge", "pkg:ledger-core", "hard"),
        ("gate", "gw:edge", "pkg:ledger-utils", "hard"),
        ("gate", "gw:edge", "pkg:ledger-gateway", "hard"),
        ("gate", "gw:edge", "pkg:ledger-metrics", "hard"),
    ]
)
lines = ["lane,parent,child,edge_kind"] + [f"{a},{b},{c},{d}" for a, b, c, d in rows]
(root / "data" / "graphs" / "edges.csv").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

rev: dict[str, list[str]] = {}
for lane, parent, child, kind in rows:
    if lane != "edge" or kind != "hard":
        continue
    rev.setdefault(child, []).append(parent)
for parents in rev.values():
    parents.sort()
node = "pkg:tainted"
hops = 0
seen = set()
while node != "svc:app":
    parents = rev.get(node, [])
    if not parents or node in seen:
        raise SystemExit(f"cannot derive hops from {node}")
    seen.add(node)
    node = parents[0]
    hops += 1
(root / "config" / "release_matrix.csv").write_text(
    f"lane,retention_hops\nedge,{hops}\ncore,1\ngate,3\n",
    encoding="utf-8",
    newline="\n",
)
print(f"repaired graphs; edge retention_hops={hops}")

arts = ["lane,coordinate"]
for a in [
    "svc:app",
    "mid:bridge",
    "mid:spur",
    "mid:fen",
    "mid:beam",
    "mid:relay",
    "mid:span",
    "mid:stem",
    "mid:ridge",
    "mid:ford",
    "mid:ledge",
    "mid:shelf",
    "mid:crest",
    "mid:cairn",
    "mid:peak",
    "mid:saddle",
    "mid:knoll",
    "mid:col",
    "mid:glen",
    "mid:mesa",
    "mid:keel",
    "mid:tor",
    "mid:crag",
    "mid:rift",
    "mid:dune",
    "mid:heath",
    "mid:scar",
    "mid:mere",
    "mid:holt",
    "mid:vale",
    "mid:apex",
    "mid:via",
    "mid:fork",
    "mid:wing",
    "mid:yoke",
    "mid:arch",
    "mid:link",
    "pkg:ledger-core",
    "pkg:ledger-utils",
    "pkg:ledger-gateway",
    "pkg:ledger-metrics",
    "pkg:legacy-nuget",
    "pkg:tainted",
    "pkg:blocked",
    "pkg:quarantine",
    "trace:soft",
    "trace:haze",
    "trace:mist",
    "trace:fog",
]:
    arts.append(f"edge,{a}")
for a in ["api:core", "pkg:ledger-core", "pkg:ledger-utils", "pkg:ledger-gateway", "pkg:ledger-metrics"]:
    arts.append(f"core,{a}")
for a in [
    "gw:edge",
    "mid:g1",
    "mid:g2",
    "pkg:ledger-core",
    "pkg:ledger-utils",
    "pkg:ledger-gateway",
    "pkg:ledger-metrics",
    "pkg:alt-a",
    "pkg:alt-b",
]:
    arts.append(f"gate,{a}")
(root / "data" / "graphs" / "artifacts.csv").write_text("\n".join(arts) + "\n", encoding="utf-8", newline="\n")

src = root / "nuget-cache" / "tainted-0.1.0-py3-none-any.whl"
for name in ("blocked-0.1.0-py3-none-any.whl", "quarantine-0.1.0-py3-none-any.whl"):
    whl = root / "nuget-cache" / name
    if not whl.exists():
        whl.write_bytes(src.read_bytes() if src.exists() else (name.encode() + b"\n"))
PY
printf '%s\n' '# emptied for nuget' > /app/legacy-nuget-notes.txt
python3 - <<'PY'
from pathlib import Path
root = Path('/app')
for rel in ('Cargo.toml', 'Cargo.lock'):
    p = root / rel
    p.write_text(p.read_text(encoding='utf-8').replace('0.12.0', '1.59.0'), encoding='utf-8', newline='\n')
PY
bash /app/scripts/release.sh
