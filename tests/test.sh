#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

TEST_DIR="${TEST_DIR:-/tests}"
cd "$TEST_DIR" || {
    echo 0 > /logs/verifier/reward.txt
    exit 0
}

/opt/verifier-venv/bin/python -m pytest --ctrf /logs/verifier/ctrf.json "$TEST_DIR/test_outputs.py" -rA -o cache_dir=/tmp/pytest_cache
rc=$?

if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
