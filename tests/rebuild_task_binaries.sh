#!/bin/bash
# Verifier-owned rebuild: copy submitted Go sources into a protected tree and
# emit fresh binaries under /tmp/verifier-bin. Never execute agent /app/bin wrappers.
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH:-/usr/bin:/bin}"

src_root="${VERIFIER_SRC:-/tmp/verifier-src}"
bin_root="${VERIFIER_BIN:-/tmp/verifier-bin}"

rm -f /app/bin/mirctl /app/bin/viewctl
rm -rf "$src_root" "$bin_root"
mkdir -p "$src_root" "$bin_root"

python3 - <<'PY'
import os
import shutil
from pathlib import Path

src = Path("/app") / "environment"
dst = Path(os.environ.get("VERIFIER_SRC", "/tmp/verifier-src"))
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(
    src,
    dst,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
)
PY

for rel in cmd/mirctl/main.go cmd/viewctl/main.go go.mod; do
  if [ -f "$src_root/$rel" ]; then
    chmod a-w "$src_root/$rel"
  fi
done
if [ -f "$src_root/go.sum" ]; then
  chmod a-w "$src_root/go.sum"
fi

cd "$src_root"
go build -o "$bin_root/mirctl" ./cmd/mirctl
go build -o "$bin_root/viewctl" ./cmd/viewctl

chmod 555 "$bin_root/mirctl" "$bin_root/viewctl"
test -x "$bin_root/mirctl"
test -x "$bin_root/viewctl"
