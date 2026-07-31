#!/bin/bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set."
  mkdir -p /logs/verifier
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

mkdir -p /logs/verifier /app/output

export PATH="/app/bin:${PATH}"

cd /app
go build -o /app/bin/tak-road /app/cmd/tak-road
rc_build=$?
if [ "$rc_build" -ne 0 ]; then
  echo "go build failed"
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

/app/bin/tak-road --scenarios /app/scenarios --config /app/config --out /app/output
rc_run=$?
if [ "$rc_run" -ne 0 ]; then
  echo "tak-road run failed"
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

cd /tests
env -u PYTHONPATH -u PYTHONHOME \
  PYTHONNOUSERSITE=1 \
  PATH="/usr/sbin:/usr/bin:/bin:/app/bin" \
  python3 -I -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -v -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
