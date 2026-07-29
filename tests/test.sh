#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
if [ ! -s /logs/verifier/ctrf.json ]; then
  cat > /logs/verifier/ctrf.json <<'JSON'
{"results":{"tool":{"name":"pytest"},"summary":{"tests":0,"passed":0,"failed":0,"pending":0,"skipped":0,"other":0,"start":0,"stop":0},"tests":[]}}
JSON
fi

if [ "$PWD" = "/" ]; then
  echo "refusing to run from /" >&2
  exit 1
fi

TEST_DIR="${TEST_DIR:-/tests}"

cd /app || { echo "cannot enter /app" >&2; exit 1; }

g++ -O2 -std=c++17 /app/main.cpp /app/shovehalf.cpp -o /tmp/shovehalf || {
  echo "build failed" >&2
  exit 1
}
chmod 755 /tmp/shovehalf

chown -R root:root "${TEST_DIR}" 2>/dev/null || true
chmod -R go-rwx "${TEST_DIR}" 2>/dev/null || true
chmod 700 "${TEST_DIR}" 2>/dev/null || true
chown -R root:root /solution 2>/dev/null || true
chmod 700 /solution 2>/dev/null || true

export PYTHONSAFEPATH=1
status=0
trap 'exit "$status"' EXIT
python3 -m pytest --ctrf /logs/verifier/ctrf.json "${TEST_DIR}/test_outputs.py" -v -rA -p no:cacheprovider --confcutdir="${TEST_DIR}"
status=$?
if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi