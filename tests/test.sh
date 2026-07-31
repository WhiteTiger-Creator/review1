#!/bin/bash
set -uo pipefail

export PATH="/root/.local/bin:/usr/local/go/bin:/go/bin:/opt/verifier-venv/bin:${PATH:-/usr/bin}"

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
printf '%s\n' '{"version":"1.0.0","results":{"summary":{"tests":0,"passed":0,"failed":0,"pending":0,"skipped":0,"other":0}}}' > /logs/verifier/ctrf.json

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

TEST_DIR="${TEST_DIR:-/tests}"

mkdir -p /opt/verifier-fixtures
cp -a "${TEST_DIR}/verifier-fixtures/." /opt/verifier-fixtures/

set +e
cd /app
bash /app/scripts/rebuild-cdnqual.sh && \
PYTHONPATH="${TEST_DIR}/verifier-support:${TEST_DIR}:${PYTHONPATH:-}" \
/opt/verifier-venv/bin/python -m pytest --ctrf /logs/verifier/ctrf.json \
  -o cache_dir=/tmp/pytest_cache \
  "${TEST_DIR}/test_outputs.py" -rA
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
