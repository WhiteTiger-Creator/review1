#!/bin/bash
set -euo pipefail

SOLUTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_FILE=""
for candidate in "$SOLUTION_DIR/solution.patch" /oracle/solution.patch /solution/solution.patch; do
  if [ -f "$candidate" ]; then PATCH_FILE="$candidate"; break; fi
done
if [ -z "$PATCH_FILE" ]; then
  echo "Oracle source patch is unavailable" >&2
  exit 1
fi

cd /app
if patch --dry-run --batch --forward -p1 < "$PATCH_FILE" >/dev/null; then
  patch --batch --forward -p1 < "$PATCH_FILE"
elif patch --dry-run --batch --reverse -p1 < "$PATCH_FILE" >/dev/null; then
  echo "Oracle patch is already applied"
else
  echo "Oracle patch does not match /app" >&2
  exit 1
fi

gofmt -w /app/cmd /app/internal
go mod verify
make clean
make build

find /app/out -mindepth 1 -maxdepth 1 -not -name '.gitkeep' -exec rm -rf {} +
/app/bin/orbit-api --db /app/data/orbit.sqlite3 --publish-dir /app/out --web /app/web --listen 127.0.0.1:18080 >/tmp/orbit-api.log 2>&1 &
api_pid=$!
cleanup() { kill "$api_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 100); do
  if python3 - <<'PY' >/dev/null 2>&1
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:18080/health', timeout=0.2) as response:
    assert response.status == 200
PY
  then break; fi
  if ! kill -0 "$api_pid" 2>/dev/null; then cat /tmp/orbit-api.log >&2; exit 1; fi
  sleep 0.05
done
/app/bin/orbit-certify --db /app/data/orbit.sqlite3 --api http://127.0.0.1:18080 --publish-dir /app/out --timeout-ms 5000
/app/bin/fft-check >/dev/null
test -s /app/out/current.json
