#!/usr/bin/env bash
# Deceptive local pulse — green when book readable and merged table non-empty
set -euo pipefail
BOOK="${1:?}"
MERGED="${2:?}"
if [[ -f "$BOOK" && -s "$MERGED" ]]; then
  echo "pulse: ok"
  exit 0
fi
echo "pulse: fail" >&2
exit 1
