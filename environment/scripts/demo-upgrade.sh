#!/usr/bin/env bash
set -euo pipefail

FAILPOINT="${1:-after-partial-copy}"
DB="${KSEAL_DB:-/app/state/store.db}"

/app/bin/opsctl reset-demo --db "$DB"
export KSEAL_FAILPOINT="$FAILPOINT"
set +e
/app/bin/opsctl upgrade --db "$DB"
exit_code=$?
set -e

if [[ "$exit_code" -ne 75 ]]; then
  echo "expected failpoint exit 75, got $exit_code" >&2
  exit 1
fi

echo "demo interrupted at $FAILPOINT"
