#!/bin/bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set."
  mkdir -p /logs/verifier
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

TEST_DIR="${TEST_DIR:-/tests}"

/opt/verifier_venv/bin/python3 -m pytest --ctrf /logs/verifier/ctrf.json "$TEST_DIR/test_outputs.py" -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
