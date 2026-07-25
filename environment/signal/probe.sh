#!/bin/bash
set -euo pipefail
ROOT="${MIRROR_ROOT:-/app/environment}"
PASS="${CYCLE:-1}"
if [ "$PASS" -eq 1 ]; then
  cat="$ROOT/fixtures/catalog_view_a.json"
else
  cat="$ROOT/fixtures/catalog_view_b.json"
fi
flags=$(python3 -c "import json;print(json.load(open('$cat'))['state_flags'])")
if [ "$flags" -ge 2 ]; then
  echo "probe_ok"
  exit 0
fi
echo "probe_fail"
exit 1
