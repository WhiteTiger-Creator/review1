#!/bin/bash
# -e is intentionally omitted so a pytest failure does not exit before the
# reward file is written.
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Rebuild happens inside pytest so compile failures still emit CTRF.
# Cap the whole verifier so a hung agent binary cannot erase the report.
/usr/bin/timeout --signal=KILL 720s python3 -m pytest \
    -o cache_dir=/tmp/pytest_cache \
    --ctrf /logs/verifier/ctrf.json \
    /tests/test_outputs.py \
    -rA
pytest_rc=$?

if [ ! -s /logs/verifier/ctrf.json ]; then
    cat > /logs/verifier/ctrf.json <<'EOF'
{"results":{"tool":{"name":"pytest"},"summary":{"tests":1,"passed":0,"failed":1,"skipped":0},"tests":[{"name":"verifier_bootstrap","status":"failed","message":"verifier did not produce pytest CTRF"}]}}
EOF
    pytest_rc=1
fi

[ "$pytest_rc" -eq 0 ]
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
