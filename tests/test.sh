#!/bin/bash
mkdir -p /logs/verifier

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set."
  exit 1
fi

chmod 700 /tests
chmod -R go-rwx /tests

/opt/pytools/bin/python -m pytest \
  --ctrf /logs/verifier/ctrf.json \
  -rA /tests/test_outputs.py
status=$?

if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
