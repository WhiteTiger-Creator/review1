#!/bin/bash
# No `set -e`: the reward write at the bottom must happen on every path.
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "error: verifier launched without a working directory" >&2
    exit 1
fi

TEST_DIR="${TEST_DIR:-/tests}"

rm -rf /app/outputs
mkdir -p /app/outputs

timeout 420s Rscript /app/analysis.R
R_STATUS=$?
if [ "$R_STATUS" -ne 0 ]; then
    echo "analysis.R exited with status $R_STATUS" >&2
    exit 1
fi

PYTHONSAFEPATH=1 /opt/verifier-venv/bin/python -I -m pytest \
    -c "$TEST_DIR/pytest.ini" \
    --rootdir="$TEST_DIR" \
    --confcutdir="$TEST_DIR" \
    -p no:cacheprovider \
    --ctrf /logs/verifier/ctrf.json \
    "$TEST_DIR/test_outputs.py" \
    -v -rA
PT_STATUS=$?
if [ "$PT_STATUS" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
