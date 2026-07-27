#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Defense-in-depth (redundant with tests/conftest.py's session-scoped
# fixture): unconditionally clear any pre-existing db/output artifacts
# before the test run starts, in case this filesystem is reused across
# sequential evaluation trials.
rm -f /app/wb.db /app/wb.db-journal /app/wb.db-wal /app/wb.db-shm
rm -rf /app/output

python3 -m pytest -o cache_dir=/tmp/pytest_cache --ctrf /logs/verifier/ctrf.json /tests/test_wb_tracker.py -rA 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
