#!/bin/bash
# Terminal-Bench Canary 7f3a9c2e
set -euo pipefail

export HOME="${HOME:-/tmp}"
if [ ! -d "$HOME" ] || [ ! -w "$HOME" ]; then
  export HOME=/tmp
fi
export GOCACHE="${GOCACHE:-/tmp/go-cache}"
mkdir -p "$GOCACHE" 2>/dev/null || true

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

for d in /app/environment /app/bin /app/output "$GOCACHE"; do
  chmod -R u+rwX,g+rwX,o+rwX "$d" 2>/dev/null || true
done

cp -f "${ROOT_DIR}/knot_p.go" /app/environment/knot/knot_p.go
cp -f "${ROOT_DIR}/vault_w.go" /app/environment/vault/vault_w.go
cp -f "${ROOT_DIR}/sieve_z.go" /app/environment/sieve/sieve_z.go

bash /app/environment/scripts/build_cqrun.sh
test -x /app/bin/cqrun

rm -rf /app/output/cohort_state
/app/bin/cqrun run --packs /app/packs --out /app/output/cohort_trace.json --state /app/output/cohort_state
test -s /app/output/cohort_trace.json

python3 - <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/environment/scripts")
from ref_kit import expected_trace

got = json.loads(Path("/app/output/cohort_trace.json").read_text(encoding="utf-8"))
exp = expected_trace()
assert got["summary"]["fence_status"] == "sealed"
assert got["summary"]["cohort_digest"] == exp["summary"]["cohort_digest"]
assert got["summary"]["resume_digest"] == exp["summary"]["resume_digest"]
assert got["summary"]["rows_total"] == exp["summary"]["rows_total"]
print("oracle emit ok", got["summary"]["cohort_digest"])
PY
