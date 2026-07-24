#!/bin/bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Set WORKDIR in Dockerfile."
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier

cd /app && make 2>&1
BUILD_RC=$?
if [ $BUILD_RC -ne 0 ]; then
    echo "Build failed with exit code $BUILD_RC"
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /app/output
/app/bin/tuf-rollout-verifier
VERIFY_RC=$?
if [ $VERIFY_RC -ne 0 ]; then
    echo "tuf-rollout-verifier failed with exit code $VERIFY_RC"
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
