#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
_on_exit() {
    if [ ! -f /logs/verifier/ctrf.json ]; then
        echo '{"results":{"summary":{"tests":0,"passed":0,"failed":1,"skipped":0},"tests":[]}}' > /logs/verifier/ctrf.json
    fi
}
trap _on_exit EXIT
if [ "$PWD" = "/" ]; then
    echo "The task image must set a working directory." >&2
    exit 0
fi
/opt/verifier-venv/bin/python -I -m pytest -o cache_dir=/tmp/pytest_cache \
    --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA --tb=short
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
