#!/bin/bash
mkdir -p /logs/verifier
rm -f /logs/verifier/ctrf.json

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set."
  printf '%s\n' '{"results":{"tool":{"name":"precondition"},"summary":{"tests":1,"passed":0,"failed":1,"pending":0,"skipped":0,"other":0},"tests":[{"name":"verifier-precondition","status":"failed","duration":0}]}}' > /logs/verifier/ctrf.json
  false
else
  cd /tests && PYTHONDONTWRITEBYTECODE=1 /opt/verifier-venv/bin/python \
    -m pytest -p no:cacheprovider --ctrf /logs/verifier/ctrf.json \
    -q /tests/test_outputs.py -rA
  pytest_status=$?
  if [ ! -s /logs/verifier/ctrf.json ]; then
    printf '%s\n' '{"results":{"tool":{"name":"precondition"},"summary":{"tests":1,"passed":0,"failed":1,"pending":0,"skipped":0,"other":0},"tests":[{"name":"verifier-precondition","status":"failed","duration":0}]}}' > /logs/verifier/ctrf.json
  fi
  test "$pytest_status" -eq 0
fi
status=$?
if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
