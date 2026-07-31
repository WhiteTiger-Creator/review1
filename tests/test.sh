#!/usr/bin/env bash
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
# The pytest suite is the sole source of the verifier reward status.
/usr/bin/python3 -m pytest /tests/test_outputs.py --tb=short --disable-warnings -rA --ctrf /logs/verifier/ctrf.json
status=$?
if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
