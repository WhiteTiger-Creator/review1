#!/bin/bash
sed -i 's/\r$//' "$0" 2>/dev/null || true
set -u

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

export PYTHONDONTWRITEBYTECODE=1

if [ "$PWD" = "/" ]; then
  echo "Error: No WORKDIR set in Dockerfile." >&2
  exit 1
fi

if [ -x /opt/venv/bin/python ]; then
  PY=/opt/venv/bin/python
else
  PY=python3
fi

cd /app || exit 1
"${PY}" -m pytest -p no:cacheprovider -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
