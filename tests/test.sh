#!/bin/sh
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
sealed_tests=/opt/verifier-run-fbf7d0c2
rm -rf "$sealed_tests"
mkdir -p "$sealed_tests"
cp /tests/test_outputs.py "$sealed_tests/test_outputs.py"
chmod -R go-rwx "$sealed_tests"
chmod -R go-rwx /tests 2>/dev/null || true
cd "$sealed_tests"
PYTHONPATH="$sealed_tests" PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1 /opt/verifier-venv/bin/python -P -m pytest -p no:cacheprovider -q -rA --ctrf /logs/verifier/ctrf.json "$sealed_tests/test_outputs.py"
test_rc=$?
if [ "$test_rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
