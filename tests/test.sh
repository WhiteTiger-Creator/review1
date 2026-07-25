#!/bin/bash
set -uo pipefail

export PATH="/opt/runtime-venv/bin:${PATH}"

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
printf '%s\n' '{"version":"1.0.0","results":{"tool":{"name":"pytest"},"summary":{"tests":0,"passed":0,"failed":0,"skipped":0},"tests":[]}}' > /logs/verifier/ctrf.json

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

cd /app || {
  echo 0 > /logs/verifier/reward.txt
  exit 1
}

bash /app/scripts/build.sh || {
  echo 0 > /logs/verifier/reward.txt
  exit 1
}

# Hidden observation sets live under tests/ only — never baked into the agent image.
HIDDEN_SRC="${TEST_DIR:-/tests}/hidden"
mkdir -p /opt/verifier-fixtures/hfsy
if [ ! -d "$HIDDEN_SRC" ]; then
  echo "Error: hidden verifier fixtures bundle missing at $HIDDEN_SRC" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi
cp -a "$HIDDEN_SRC/." /opt/verifier-fixtures/hfsy/
chmod -R 700 /opt/verifier-fixtures/hfsy
for obs in obs-k4m1 obs-p9w2 obs-r7n3; do
  if [ ! -d "/opt/verifier-fixtures/hfsy/$obs" ]; then
    echo "Error: missing hidden observation fixture directory: /opt/verifier-fixtures/hfsy/$obs" >&2
    echo 0 > /logs/verifier/reward.txt
    exit 1
  fi
done

set +e
/opt/runtime-venv/bin/python -m pytest -rA -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json "${TEST_DIR:-/tests}/test_outputs.py"
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
