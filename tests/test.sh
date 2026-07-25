#!/usr/bin/env bash
set +e

mkdir -p /logs/verifier
pytest -p no:cacheprovider -rA /tests/test_pod_source_lock.py
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
