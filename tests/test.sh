#!/bin/bash
# Verifier dependencies are baked into environment/Dockerfile; nothing is installed here.
# Kept free of bashisms so the reward file is written whichever shell runs this.
set -u

mkdir -p /logs/verifier

python -m pytest -o cache_dir=/tmp/pytest_cache --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
