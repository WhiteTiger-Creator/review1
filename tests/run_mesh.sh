#!/bin/bash
# Verifier helper: regenerate via the station under /app/environment
set -euo pipefail
ROOT=/app/environment
export ROOT
case "${1:?}" in
  mesh)
    bash "$ROOT/scripts/s1.sh"
    ;;
  flare)
    bash "$ROOT/scripts/s2.sh"
    ;;
  rewind)
    bash "$ROOT/scripts/s3.sh"
    ;;
  *)
    echo "unknown target: $1" >&2
    exit 2
    ;;
esac
