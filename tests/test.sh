#!/bin/bash
set -uo pipefail
chmod 0755 "$0" 2>/dev/null || true

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

APP_DIR="${APP_DIR:-/app}"
TEST_DIR="${TEST_DIR:-/tests}"
FIXTURES_DIR="${FIXTURES_DIR:-${TEST_DIR}/fixtures}"
export APP_DIR TEST_DIR FIXTURES_DIR
export NUGETFIX_AGENT="${NUGETFIX_AGENT:-nugetfixagent}"

if [ -d /tests ]; then
  chown -R root:root /tests 2>/dev/null || true
  chmod 700 /tests 2>/dev/null || true
  find /tests -type d -exec chmod 700 {} + 2>/dev/null || true
  find /tests -type f -exec chmod 600 {} + 2>/dev/null || true
fi

unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE || true
export PYTHONNOUSERSITE=1
cd "$TEST_DIR" || exit 1
/opt/venv/bin/python -s -m pytest --ctrf /logs/verifier/ctrf.json \
  -o cache_dir=/tmp/nugetfix-pytest-cache "$TEST_DIR/test_outputs.py" -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
