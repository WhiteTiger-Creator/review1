#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

rc=1
trap 'exit "${rc}"' EXIT

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    rc=1
    exit 1
fi

PYTHON_BIN="/opt/verifier-venv/bin/python"
export PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:${PATH}"
export CARGO_INCREMENTAL=0
export VAULT_MAZE_LOCK_BIN="/app/target/release/vault-maze-lock"

cd /app

rm -rf /app/target
rm -f /app/output/release_report.json /app/output/release_report.json.tmp

set +e
/usr/local/bin/cargo build --release --locked --offline
build_rc=$?
set -e
if [ "$build_rc" -ne 0 ]; then
  echo 0 > /logs/verifier/reward.txt
  rc="$build_rc"
  exit "$build_rc"
fi

if [ ! -x "${VAULT_MAZE_LOCK_BIN}" ]; then
  echo "Error: release binary missing at ${VAULT_MAZE_LOCK_BIN}"
  echo 0 > /logs/verifier/reward.txt
  rc=1
  exit 1
fi

set +e
COLLECT_OUT="$(
  "${PYTHON_BIN}" -I -m pytest \
    -c /dev/null \
    --rootdir=/tests \
    --confcutdir=/tests \
    --collect-only \
    -q \
    /tests/test_outputs.py 2>&1
)"
collect_rc=$?
set -e

if [ "$collect_rc" -ne 0 ] || ! echo "${COLLECT_OUT}" | grep -q "28 tests collected"; then
  echo "Error: expected exactly 28 collected tests (collect_rc=${collect_rc})"
  echo "${COLLECT_OUT}"
  echo 0 > /logs/verifier/reward.txt
  rc=1
  exit 1
fi

set +e
"${PYTHON_BIN}" -I -m pytest \
  -c /dev/null \
  --rootdir=/tests \
  --confcutdir=/tests \
  -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json \
  /tests/test_outputs.py \
  -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
