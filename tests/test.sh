#!/bin/bash
mkdir -p /logs/verifier

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set."
  exit 1
fi

chmod 700 /tests
chmod -R go-rwx /tests

# Run from the sealed test directory in isolated mode so nothing the candidate
# leaves in its own tree can be imported ahead of the real pytest.
cd /tests

/opt/pytools/bin/python -I -m pytest \
  --rootdir=/tests \
  -p no:cacheprovider \
  --ctrf /logs/verifier/ctrf.json \
  -rA /tests/test_outputs.py
status=$?

if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
