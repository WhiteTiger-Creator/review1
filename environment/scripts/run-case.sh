#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/var/lib/mint}"
CASE="${2:?case toml required}"
OUT="${3:-/output}"

export CARGO_HOME=/opt/cargo
export PATH="/usr/local/cargo/bin:${PATH}"

/app/scripts/reset-visible-store.sh "$ROOT"
python3 - <<'PY' "$CASE" "$ROOT"
import json, shutil, subprocess, sys, tomllib
from pathlib import Path

case_path, root = Path(sys.argv[1]), Path(sys.argv[2])
case = tomllib.loads(case_path.read_text())
seed = case.get("seed", 1)
subprocess.run(
    ["/tests/verifier-driver/target/release/rstore-verifier", "materialize", str(seed), str(root)],
    check=True,
)
for step in case.get("steps", []):
    cmd = step["cmd"]
    subprocess.run(cmd, check=True)
PY
if [ -f "$OUT/store-inventory.json" ]; then
  /app/scripts/compare-inventory.sh "$OUT/store-inventory.json" "${CASE%.toml}.expected.json" || true
fi
