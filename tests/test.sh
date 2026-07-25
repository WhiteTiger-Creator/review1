#!/bin/bash
set -uo pipefail

# Test-side dependencies are installed in environment/Dockerfile.
# Add task-specific Python packages there, not here.

mkdir -p /logs/verifier

# Run pytest isolated from whatever the agent left in the work tree:
# PYTHONSAFEPATH keeps the current directory off sys.path, running from /tmp
# keeps the rootdir out of /app, and importlib import mode avoids inserting
# test/rootdir paths. Together these stop a stray file the agent may have left
# in /app from shadowing a standard-library import.
export PYTHONSAFEPATH=1
cd /tmp

# Produce the reward file (REQUIRED) - the harness reads this, not the exit code.
python -m pytest -o cache_dir=/tmp/pytest_cache -p no:cacheprovider \
  --import-mode=importlib \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
