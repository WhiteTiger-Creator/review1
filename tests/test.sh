#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Check if we're in a valid working directory
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

SRC_FILES="/app/ct.go /app/merkle.go /app/sct.go /app/verifier.go"

# ── 1. Verify the daemon compiles cleanly ────────────────────────────────────
echo "==> Building CT verifier daemon..."
if ! timeout 90 go build -o /tmp/ctverifier . 2>&1; then
    echo "ERROR: go build failed"
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

# ── 2. Copy test runner into app directory and compile (no main.go) ──────────
cp /tests/test_main.go /app/test_runner.go

echo "==> Building standard test binary..."
if ! go build -o /tmp/test_ct $SRC_FILES /app/test_runner.go 2>&1; then
    echo "ERROR: test binary build failed"
    rm -f /app/test_runner.go
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

echo "==> Building race-detector test binary..."
if ! CGO_ENABLED=1 go build -race -o /tmp/test_ct_race $SRC_FILES /app/test_runner.go 2>&1; then
    echo "ERROR: race-detector test binary build failed"
    rm -f /app/test_runner.go
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

rm -f /app/test_runner.go

# ── 3. Run pytest ────────────────────────────────────────────────────────────
echo "==> Running pytest..."
python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?

if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
