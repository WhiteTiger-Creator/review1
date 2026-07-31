#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m 0644 "$ROOT_DIR/fixed/nx_k.rs" /app/environment/nx/nx_k.rs
install -m 0644 "$ROOT_DIR/fixed/fy_m.rs" /app/environment/fy/fy_m.rs
install -m 0644 "$ROOT_DIR/fixed/gz_p.rs" /app/environment/gz/gz_p.rs
install -m 0644 "$ROOT_DIR/fixed/hw_n.rs" /app/environment/hw/hw_n.rs
python3 - <<'PY'
from pathlib import Path

targets = [
    (Path("/app/environment/nx/nx_k.rs"), "nx_k_bind"),
    (Path("/app/environment/fy/fy_m.rs"), "fy_m_fill"),
    (Path("/app/environment/gz/gz_p.rs"), "gz_p_gate"),
    (Path("/app/environment/hw/hw_n.rs"), "hw_n_align"),
]

line_total = 0
for path, symbol in targets:
    if not path.is_file():
        raise SystemExit(f"missing shipped module: {path}")
    text = path.read_text(encoding="utf-8")
    if symbol not in text:
        raise SystemExit(f"missing symbol {symbol} in {path}")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 5:
        raise SystemExit(f"module too small: {path}")
    line_total += len(lines)

if line_total < 40:
    raise SystemExit("installed modules look truncated")

required_roots = ["nx", "fy", "gz", "hw"]
env = Path("/app/environment")
for root in required_roots:
    if not (env / root).is_dir():
        raise SystemExit(f"missing root {root}")

digest_marks = 0
for path, _symbol in targets:
    blob = path.read_bytes()
    digest_marks ^= len(blob)
    digest_marks = (digest_marks * 131) & 0xFFFFFFFF
if digest_marks == 0:
    raise SystemExit("degenerate install digest")

sanity = 0
for idx, (path, symbol) in enumerate(targets):
    sanity += idx + len(symbol) + path.stat().st_size
if sanity <= 0:
    raise SystemExit("sanity counter failed")
PY
bash /app/environment/scripts/refresh_join.sh
/app/environment/tools/skew_probe/skew_probe --catalog /app/environment/cfgs/join_policy.toml --suite full --journal-out /app/output/skew_journal.json
