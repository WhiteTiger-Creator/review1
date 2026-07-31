#!/bin/bash

# Verifier dependencies are installed in environment/Dockerfile (allow_internet = false).
set -uo pipefail

mkdir -p /logs/verifier
# Prewrite a failing reward so a reward file always exists, even if pytest is killed.
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Set a WORKDIR in the Dockerfile." >&2
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi

TEST_DIR="${TEST_DIR:-/tests}"

# PYTHONSAFEPATH keeps the working directory (/app) off sys.path, so a stray file the agent may
# have written under /app cannot shadow a stdlib module and crash the verifier.
PYTHONSAFEPATH=1 python -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json "$TEST_DIR/test_outputs.py" -rA
RC=$?

if [ "$RC" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
