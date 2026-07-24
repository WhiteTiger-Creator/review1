#!/usr/bin/env bash
set -euo pipefail

mkdir -p /logs/verifier

python3 -m venv /opt/verifier_venv
/opt/verifier_venv/bin/pip install \
    --no-cache-dir \
    --no-index \
    --find-links=/tests/verifier-wheels \
    --require-hashes \
    --no-deps \
    -r /tests/requirements.lock

export PATH="/opt/verifier_venv/bin:${PATH}"

if [ "${PWD:-/}" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in the Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

set +e
pytest -rA /tests/test_outputs.py
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
