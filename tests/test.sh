#!/usr/bin/env bash
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1

readonly TEST_ROOT="${TEST_DIR:-/tests}"

chmod 1777 /logs
install -d -m 0700 -o 0 -g 0 /logs/verifier
chown 0:0 /logs/verifier
chmod 0700 /logs/verifier
rm -f -- /logs/verifier/reward.txt /logs/verifier/ctrf.json
echo 0 > /logs/verifier/reward.txt

run_verifier() {
    if [ "$(pwd)" != "/app" ]; then
        echo "Verifier must run from /app" >&2
        return 1
    fi

    PYTHONPATH="$TEST_ROOT" /opt/arena-venv/bin/python -m pytest \
        -o cache_dir=/tmp/pytest-cache \
        --ctrf /logs/verifier/ctrf.json \
        "$TEST_ROOT/test_outputs.py" -rA
}

run_verifier
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
