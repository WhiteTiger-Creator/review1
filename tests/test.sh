#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

# Build the agent's submission. A failed or missing build just means the
# binary won't exist for the behavioral tests below, which then fail
# normally through pytest rather than aborting the whole verifier here.
cargo build --release --offline --manifest-path /app/Cargo.toml || true

# Compile the independent ground-truth checker the tests cross-check
# against. This is verifier-owned reference code, not the agent's — it
# lives under tests/, which is never copied into the environment image and
# never visible to the agent.
rustc -O --edition 2021 /tests/reference_check.rs -o /tmp/reference_check

python -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
RC=$?

if [ "$RC" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
