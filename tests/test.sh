#!/bin/sh

mkdir -p /logs/verifier

if [ "$PWD" = "/" ]; then
  echo "Error: no working directory set"
  exit 1
fi

make -C /app clean || true

export PYTHONDONTWRITEBYTECODE=1

python3 -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json \
  /tests/test_kiln_parcel_engraver.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
