#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
if [ "$PWD" = "/" ]; then echo "Error: No working directory set."; echo 0 > /logs/verifier/reward.txt; exit 1; fi
PY="/opt/test-venv/bin/python3"; if [ ! -x "$PY" ]; then PY="$(command -v python3)"; fi
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$PY" -I -m pytest -rA -p no:cacheprovider --noconftest --confcutdir="$TEST_DIR" "$TEST_DIR/test_outputs.py"
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
