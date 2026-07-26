#!/bin/bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier /app/output

cd /app/bandit && go build -o /app/bin/ips-eval ./cmd/ipseva 2>&1
if [ $? -ne 0 ]; then
    echo "Build failed"
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

/app/bin/ips-eval \
    --data /app/data \
    --features /app/features \
    --models /app/models \
    --config /app/config/eval.json \
    --out /app/output 2>&1
if [ $? -ne 0 ]; then
    echo "ips-eval failed"
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
