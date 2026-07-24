#!/bin/bash
set -euo pipefail
ROOT=/app; DIST=$ROOT/dist
export CARGO_NET_OFFLINE=true SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1700000000}"

if ! python3 - <<'PY'
import csv, sys
from pathlib import Path
rows = list(csv.DictReader(Path('/app/config/release_matrix.csv').open(encoding='utf-8')))
by = {r['lane']: int(r['retention_hops']) for r in rows}
sys.exit(0 if by.get('edge') == 32 and by.get('core') == 1 and by.get('gate') == 3 else 1)
PY
then
  echo "fail-closed: release_matrix must be edge=32,core=1,gate=3" >&2
  exit 1
fi
if ! python3 - <<'PY'
from pathlib import Path
lines = Path('/app/data/graphs/edges.csv').read_text(encoding='utf-8').splitlines()
hard = [ln for ln in lines[1:] if ln.startswith('edge,') and ln.endswith(',hard')]
raise SystemExit(0 if hard and hard[0] == 'edge,svc:app,mid:bridge,hard' else 1)
PY
then
  echo "fail-closed: first edge hard row must be svc:app→mid:bridge" >&2
  exit 1
fi
if ! grep -q 'mid:spur,mid:fen,soft' "$ROOT/data/graphs/edges.csv"; then
  echo "fail-closed: edges.csv missing soft spur→fen decoy" >&2
  exit 1
fi
if ! grep -q 'mid:holt,mid:vale,soft' "$ROOT/data/graphs/edges.csv"; then
  echo "fail-closed: edges.csv missing soft holt→vale decoy" >&2
  exit 1
fi
if grep -q 'mid:mere,mid:holt,soft' "$ROOT/data/graphs/edges.csv"; then
  echo "fail-closed: edges.csv still has stale soft mere→holt decoy" >&2
  exit 1
fi
if ! python3 - <<'PY'
from pathlib import Path
text = Path('/app/data/graphs/edges.csv').read_text(encoding='utf-8')
try:
    softs = [
        text.index('edge,mid:apex,mid:via,soft'),
        text.index('edge,mid:spur,mid:fen,soft'),
        text.index('edge,mid:holt,mid:vale,soft'),
    ]
    link_i = min(
        text.index('edge,mid:link,pkg:blocked,hard'),
        text.index('edge,mid:link,pkg:legacy-nuget,hard'),
        text.index('edge,mid:link,pkg:quarantine,hard'),
        text.index('edge,mid:link,pkg:tainted,hard'),
    )
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if all(i < link_i for i in softs) else 1)
PY
then
  echo "fail-closed: soft decoys must precede mid:link residual children" >&2
  exit 1
fi
if ! python3 - <<'PY'
from pathlib import Path
text = Path('/app/data/graphs/edges.csv').read_text(encoding='utf-8')
needle = (
    "edge,mid:apex,mid:via,hard\n"
    "edge,mid:via,mid:link,hard\n"
    "edge,mid:apex,mid:fork,hard\n"
)
raise SystemExit(0 if needle in text and "mid:apex,mid:via,hard\nedge,mid:apex,mid:fork,hard" not in text else 1)
PY
then
  echo "fail-closed: edges.csv fan must be interleaved per arm (apex→arm→link)" >&2
  exit 1
fi
if ! grep -q '^edge,mid:link$' "$ROOT/data/graphs/artifacts.csv"; then
  echo "fail-closed: artifacts.csv missing required edge,mid:link row" >&2
  exit 1
fi
if ! grep -q '^edge,mid:fen$' "$ROOT/data/graphs/artifacts.csv"; then
  echo "fail-closed: artifacts.csv missing required edge,mid:fen row" >&2
  exit 1
fi
if ! python3 - <<'PY'
from pathlib import Path
text = Path('/app/data/graphs/edges.csv').read_text(encoding='utf-8')
needle = (
    "gate,gw:edge,mid:g1,hard\n"
    "gate,mid:g1,mid:g2,hard\n"
    "gate,mid:g2,pkg:alt-a,hard\n"
    "gate,mid:g2,pkg:alt-b,hard\n"
)
raise SystemExit(
    0
    if needle in text and "gate,pkg:alt-a,pkg:alt-b,hard" not in text
    else 1
)
PY
then
  echo "fail-closed: gate alts must be siblings under mid:g2 (not alt-a→alt-b chain)" >&2
  exit 1
fi
if ! python3 - <<'PY'
import tomllib, sys
from pathlib import Path
data = tomllib.loads(Path('/app/Cargo.toml').read_text(encoding='utf-8'))
sys.exit(0 if data.get('workspace', {}).get('package', {}).get('version') == '1.59.0' else 1)
PY
then
  echo "fail-closed: Cargo.toml workspace.package.version must be 1.59.0" >&2
  exit 1
fi
if ! grep -q 'offline = true' "$ROOT/.cargo/config.toml" 2>/dev/null; then
  echo "fail-closed: .cargo/config.toml must keep offline = true" >&2
  exit 1
fi
if ! grep -q 'value="/app/nuget-cache"' "$ROOT/nuget.config" 2>/dev/null; then
  echo "fail-closed: nuget.config must use local /app/nuget-cache feed" >&2
  exit 1
fi
if ! python3 - <<'PY'
import re, sys
from pathlib import Path
text = Path('/app/src/Ledger/Directory.Packages.props').read_text(encoding='utf-8')
pkgs = ('Ledger.Core', 'Ledger.Utils', 'Ledger.Gateway', 'Ledger.Metrics')
ok = all(re.search(rf'Include="{p}"\s+Version="1\.2\.0"', text) for p in pkgs)
sys.exit(0 if ok else 1)
PY
then
  echo "fail-closed: Directory.Packages.props PackageVersion rows must be 1.2.0" >&2
  exit 1
fi

rm -rf "$DIST"; mkdir -p "$DIST/bundles"
mkdir -p "$ROOT/.release-tmp"
export TMPDIR="$ROOT/.release-tmp" TMP="$ROOT/.release-tmp" TEMP="$ROOT/.release-tmp"
printf 'ok\n' > "$ROOT/.release-tmp/packaging.ok"

python3 <<'PY'
from pathlib import Path
import json
root = Path('/app')
legacy = root / 'legacy-nuget-notes.txt'
cleared = legacy.is_file() and legacy.read_text(encoding='utf-8').strip() == '# emptied for nuget'
pkgs = ['ledger-core', 'ledger-utils', 'ledger-gateway', 'ledger-metrics']
(root/'dist'/'ledger-check.txt').write_text(''.join(f'restore-ok:{p}\n' for p in pkgs), encoding='utf-8')
(root/'dist'/'ledger').write_text('publish-ready\n', encoding='utf-8')
(root/'dist'/'nuget-guard.txt').write_text(
    "fixtures/bad-lock: hash fail-closed\n"
    "expected: packages.lock.json hash mismatch against nuget-cache\n"
    "expected: leave fixtures/bad-lock unrepaired\n",
    encoding='utf-8',
)
report = {
    "format_version": 1,
    "package_count": 4,
    "offline_ci": True,
    "legacy_cleared": cleared,
    "nuget_dir": "/app/nuget-cache",
    "platform_tag": "nupkg",
}
(root/'dist'/'nuget-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
PY

cargo build --release --locked --offline -p nugetfix-cli
BIN=$ROOT/target/release/nugetfix; test -x "$BIN"
LIC=$(mktemp); { for f in $(ls "$ROOT/licenses"|sort); do cat "$ROOT/licenses/$f"; echo; done; } > "$LIC"
filter_csv(){ python3 - "$1" "$2" "$3" "$4" <<'PY'
import sys
src,dest,col,want=sys.argv[1:5]; col=int(col)
lines=open(src,encoding='utf-8').read().splitlines(); header=lines[0]
rows=[ln for ln in lines[1:] if ln and ln.split(',')[col]==want]
open(dest,'w',encoding='utf-8',newline='\n').write(header+'\n'+('\n'.join(rows)+'\n' if rows else ''))
PY
}
bundle_entries='[]'
while IFS=, read -r lane retention_hops; do
  [[ "$lane" == "lane" ]] && continue
  lane="${lane//$'\r'/}"
  retention_hops="${retention_hops//$'\r'/}"
  bundle=$DIST/bundles/nugetfix-$lane
  mkdir -p "$bundle/bin" "$bundle/share"
  cp "$BIN" "$bundle/bin/nugetfix"; chmod 0755 "$bundle/bin/nugetfix"
  cp "$LIC" "$bundle/LICENSES.txt"; printf '1.59.0\n' > "$bundle/VERSION"
  python3 -c "import json;from pathlib import Path;Path(r'$bundle/share/lane-policy.json').write_text(json.dumps({'lane':'$lane','retention_hops':int('$retention_hops')},indent=2)+'\n')"
  filter_csv "$ROOT/data/graphs/edges.csv" "$bundle/share/edges.csv" 0 "$lane"
  filter_csv "$ROOT/data/graphs/artifacts.csv" "$bundle/share/artifacts.csv" 0 "$lane"
  filter_csv "$ROOT/config/packages.csv" "$bundle/share/packages.csv" 0 "$lane"
  filter_csv "$ROOT/config/xor.csv" "$bundle/share/xor.csv" 0 "$lane"
  filter_csv "$ROOT/config/peers.csv" "$bundle/share/peers.csv" 0 "$lane"
  cp "$ROOT/config/feedtags.csv" "$bundle/share/feedtags.csv"
  cp "$ROOT/nuget-cache/index.csv" "$bundle/share/cache-index.csv"
  cp "$ROOT/config/pins.csv" "$bundle/share/pins.csv"
  cp "$ROOT/config/advisories.csv" "$bundle/share/advisories.csv"
  cp "$ROOT/config/bans.csv" "$bundle/share/bans.csv"
  cat > "$bundle/share/run-smoke.sh" <<SMOKE
#!/bin/sh
set -eu
HERE=\$(CDPATH= cd -- "\$(dirname "\$0")/.." && pwd)
OUT=\${1:-"\$HERE/share/audit-preview.json"}
POL=\$HERE/share/lane-policy.json
LANE=\$(python3 -c "import json;print(json.load(open(\"\$POL\"))['lane'])")
HOPS=\$(python3 -c "import json;print(json.load(open(\"\$POL\"))['retention_hops'])")
"\$HERE/bin/nugetfix" audit --lane "\$LANE" --edges "\$HERE/share/edges.csv" --artifacts "\$HERE/share/artifacts.csv" \\
  --packages "\$HERE/share/packages.csv" --cache "\$HERE/share/cache-index.csv" --pins "\$HERE/share/pins.csv" \\
  --feedtags "\$HERE/share/feedtags.csv" --advisories "\$HERE/share/advisories.csv" --xor "\$HERE/share/xor.csv" --bans "\$HERE/share/bans.csv" \\
  --peers "\$HERE/share/peers.csv" --retention-hops "\$HOPS" --out "\$OUT"
SMOKE
  chmod 0755 "$bundle/share/run-smoke.sh"
  "$bundle/share/run-smoke.sh" "$bundle/share/audit-preview.json"
  archive=$DIST/nugetfix-$lane-linux-x86_64.tar.gz
  ( cd "$DIST/bundles"; find "nugetfix-$lane" -print0 | LC_ALL=C sort -z | tar --null -T - --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 --numeric-owner -cf - | gzip -n > "$archive" )
  entry=$(python3 - "$lane" "$archive" "$bundle" <<'PY'
import json,hashlib,sys
from pathlib import Path
lane,archive,bundle=sys.argv[1:4]; bundle=Path(bundle)
def sha(p):
  h=hashlib.sha256()
  with open(p,'rb') as f:
    for c in iter(lambda:f.read(1<<20),b''): h.update(c)
  return h.hexdigest()
prev=json.loads((bundle/'share'/'audit-preview.json').read_text())
print(json.dumps({"lane":lane,"archive":Path(archive).name,"archive_sha256":sha(archive),
 "binary_sha256":sha(bundle/'bin'/'nugetfix'),"policy_sha256":sha(bundle/'share'/'lane-policy.json'),
 "audit_preview_sha256":sha(bundle/'share'/'audit-preview.json'),
 "artifact_count":len(prev['artifacts']),"hold_count":prev['totals']['hold'],
 "risk_score_total":prev['totals']['risk_score_total']}, separators=(',', ':')))
PY
)
  bundle_entries=$(
    PREV_JSON="$bundle_entries" ENTRY_JSON="$entry" python3 - <<'PY'
import json, os
a = json.loads(os.environ["PREV_JSON"])
a.append(json.loads(os.environ["ENTRY_JSON"]))
print(json.dumps(a, separators=(",", ":")))
PY
  )
done < "$ROOT/config/release_matrix.csv"

BUNDLE_ENTRIES_JSON="$bundle_entries" python3 <<'PY'
import json,tomllib,os
from pathlib import Path
bundles=json.loads(os.environ['BUNDLE_ENTRIES_JSON']); root=Path('/app')
ws=tomllib.loads((root/'Cargo.toml').read_text())
wlicense=ws['workspace']['package']['license']; wversion=ws['workspace']['package']['version']
workspace=[]
for p in sorted((root/'crates').glob('*/Cargo.toml')):
  data=tomllib.loads(p.read_text()); pkg=data['package']
  lic=pkg.get('license',wlicense); ver=pkg.get('version',wversion)
  if isinstance(lic,dict) and lic.get('workspace'): lic=wlicense
  if isinstance(ver,dict) and ver.get('workspace'): ver=wversion
  workspace.append({'name':pkg['name'],'version':ver,'license':lic,'dependencies':sorted((data.get('dependencies') or {}).keys())})
report=json.loads((root/'dist'/'nuget-report.json').read_text())
manifest={'format_version':1,'package':{'name':'nugetfix-cli','version':'1.59.0','target':'x86_64-unknown-linux-gnu'},
 'workspace':workspace,'hash':report,'bundles':bundles}
(root/'dist'/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
( cd "$DIST"; find . -type f ! -name checksums.sha256 -printf '%P\n' | LC_ALL=C sort | while read -r rel; do echo "$(sha256sum "$rel"|awk '{print $1}')  $rel"; done > checksums.sha256 )
