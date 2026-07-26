#!/usr/bin/env bash
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
printf '%s\n' '{"version":"1.0.0","results":{"summary":{"tests":0,"passed":0,"failed":0,"pending":0,"skipped":0,"other":0}}}' > /logs/verifier/ctrf.json

if [ "$PWD" = "/" ]; then
echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
exit 1
fi

set +e
PYTHONPATH="${TEST_DIR:-/tests}/verifier-support${PYTHONPATH:+:$PYTHONPATH}" \
  /opt/verifier-venv/bin/python -m pytest -rA -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json "${TEST_DIR:-/tests}/test_outputs.py"
rc=$?
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
