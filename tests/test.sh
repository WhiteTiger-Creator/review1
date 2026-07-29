#!/usr/bin/env bash
set -uo pipefail

rc=1
trap 'exit "$rc"' EXIT

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script." >&2
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    false
else
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt

    export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    unset PYTHONPATH PYTHONHOME
    export PYTHONSAFEPATH=1
    cd /tests

    /usr/bin/python3 -m pytest -c /dev/null --confcutdir=/tests /tests/test_outputs.py /tests/test_hard.py /tests/test_harder.py -rA
fi
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
