#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1 && [[ -x /usr/bin/python3 ]]; then
  export PATH="/usr/bin:${PATH}"
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on PATH" >&2
  exit 127
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

install -m 0755 "$ROOT_DIR/fixed_op_k7.sh" /app/environment/n4/harbor/op_k7.sh
install -m 0755 "$ROOT_DIR/fixed_merge_q3.sh" /app/environment/r9/lattice/merge_q3.sh
install -m 0755 "$ROOT_DIR/fixed_recalc_v2.sh" /app/environment/w2/vapor/recalc_v2.sh
install -m 0755 "$ROOT_DIR/fixed_a3.sh" /app/environment/cmd/a3.sh
install -m 0755 "$ROOT_DIR/fixed_a1.sh" /app/environment/cmd/a1.sh
install -m 0755 "$ROOT_DIR/fixed_s1.sh" /app/environment/scripts/s1.sh
install -m 0755 "$ROOT_DIR/fixed_s3.sh" /app/environment/scripts/s3.sh

# Ensure companion wrappers stay executable after module swaps.
python3 <<'PY'
from pathlib import Path

root = Path("/app/environment")
for rel in (
    "cmd/z1.sh",
    "cmd/z2.sh",
    "cmd/z3.sh",
    "cmd/a1.sh",
    "cmd/a2.sh",
    "cmd/a3.sh",
    "scripts/s1.sh",
    "scripts/s2.sh",
    "scripts/s3.sh",
):
    path = root / rel
    path.chmod(path.stat().st_mode | 0o111)
for folder in ("n4/harbor", "r9/lattice", "w2/vapor"):
    for path in (root / folder).glob("*.sh"):
        path.chmod(path.stat().st_mode | 0o111)

scratch = root / "scratch"
if scratch.exists():
    for child in scratch.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
        else:
            child.unlink()
scratch.mkdir(parents=True, exist_ok=True)
out = Path("/app/output")
out.mkdir(parents=True, exist_ok=True)
for cache in out.glob("vz/*.cache"):
    cache.unlink()
PY

ROOT=/app/environment bash /app/environment/scripts/s1.sh
