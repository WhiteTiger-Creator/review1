#!/bin/bash
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
rm -f /logs/verifier/ctrf.json

TEST_DIR="${TEST_DIR:-/tests}"
cd "$TEST_DIR" || exit 0

PYTHONSAFEPATH=1 python3 -P -m pytest -p no:cacheprovider -rA \
    --ctrf /logs/verifier/ctrf.json \
    "$TEST_DIR/test_outputs.py"
status=$?

if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
