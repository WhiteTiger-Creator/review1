#!/bin/bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier

cd /app && make clean && make
build_rc=$?
if [ "$build_rc" -ne 0 ]; then
    echo "build failed"
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /app/output
/app/bin/basin-flux
run_rc=$?
if [ "$run_rc" -ne 0 ]; then
    echo "runtime failed"
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -v -rA
rc=$?

if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
