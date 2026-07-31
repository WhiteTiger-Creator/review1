#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi
cd /app
# Remove anything already built so a stale or hand-placed binary can never be
# run: the only book the checks may see is the one this build makes from
# /app/src on this run. A failed build stops the run outright.
rm -rf /app/build
mkdir -p /app/build
if ! g++ -O2 -std=c++17 -o /app/build/sedgemere /app/src/*.cpp; then
    echo "Error: the book did not build; refusing to check a stale or absent one."
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi
if [ ! -x /app/build/sedgemere ]; then
    echo "Error: the build reported success but produced nothing."
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi
TEST_DIR="${TEST_DIR:-/tests}"
# The process the levels come from is carried in the checks themselves. Copy
# them somewhere only this script can reach and run them there, so nothing the
# book can read while it runs says how the levels are made.
PRIVATE=$(mktemp -d)
chmod 700 "$PRIVATE"
cp "$TEST_DIR/test_outputs.py" "$PRIVATE/test_outputs.py"
rm -f "$TEST_DIR/test_outputs.py" 2>/dev/null || true
rm -rf "$TEST_DIR/__pycache__" 2>/dev/null || true
cd "$PRIVATE"
python3 -P -m pytest -o cache_dir=/tmp/pytest_cache \
  --rootdir="$PRIVATE" --confcutdir="$PRIVATE" \
  --ctrf /logs/verifier/ctrf.json "$PRIVATE/test_outputs.py" -rA
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
