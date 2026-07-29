#!/bin/bash
set -euo pipefail
ROOT="${MIRROR_ROOT:-/app/environment}"
OUT="${OUTPUT_DIR:-/app/output}"
export MIRROR_ROOT="$ROOT"
mkdir -p "$OUT"
CYCLES="${CYCLE_COUNT:-2}"
for ((i=1; i<=CYCLES; i++)); do
  export CYCLE="$i"
  if [ "$i" -gt 1 ]; then
    export APPEND_EXPORT=1
  else
    unset APPEND_EXPORT
  fi
  /app/bin/mirctl run "$OUT"
done
