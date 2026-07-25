#!/bin/bash

mkdir -p /logs/verifier
export SPANFORGE_ROOT=/opt/spanforge

# Install verifier-only dependencies here (not during image build).
if [ ! -x /opt/verifier_venv/bin/pytest ]; then
    python3 -m venv /opt/verifier_venv
    /opt/verifier_venv/bin/pip install \
        --no-index \
        --find-links=/verifier-wheels \
        --require-hashes \
        --no-deps \
        -r /opt/verifier-requirements.lock
fi

export PATH="/opt/verifier_venv/bin:$PATH"

cd /tests || exit 1

pytest -rA /tests/test_outputs.py
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
