#!/bin/bash
set -euo pipefail
cp /solution/solution.c /app/src/recovered.c
cd /app
make clean
make recovered
test -x /app/build/recovered
for trace in /app/inputs/*.bin; do
  set +e
  /app/build/recovered < "$trace" > /tmp/candidate.out
  candidate_code=$?
  set -e
  if [ ! -x /app/bin/timers ]; then
    continue
  fi
  set +e
  /app/bin/timers < "$trace" > /tmp/reference.out
  reference_code=$?
  set -e
  cmp /tmp/candidate.out /tmp/reference.out
  if [ "$candidate_code" -ne "$reference_code" ]; then
    echo "exit status mismatch on $trace" >&2
    exit 1
  fi
done
