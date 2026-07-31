#!/usr/bin/env bash
# Oracle — edgekiln-tcpfeat-anvil
set -euo pipefail
PATH="/usr/local/go/bin:${PATH}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

install -m 0644 "${ROOT_DIR}/files/framestream/parse.go" /app/framestream/parse.go
install -m 0644 "${ROOT_DIR}/files/duplexstitch/reassemble.go" /app/duplexstitch/reassemble.go
install -m 0644 "${ROOT_DIR}/files/tensorloom/features.go" /app/tensorloom/features.go
install -m 0644 "${ROOT_DIR}/files/entropymilli/entropy.go" /app/entropymilli/entropy.go
install -m 0644 "${ROOT_DIR}/files/l2anvil/ridge.go" /app/l2anvil/ridge.go

bash /app/scripts/rebuild-cdnqual.sh
test -x /app/bin/cdnqual

rm -rf /app/qualitycast
mkdir -p /app/qualitycast
/app/bin/cdnqual run-forge --wire /app/polbay/run_manifest.json

python3 - <<'PY'
import json
from pathlib import Path
out = Path("/app/qualitycast")
feat = (out / "session_features.jsonl").read_text()
ledger = json.loads((out / "eval_ledger.json").read_text())
digest = json.loads((out / "feature_digest.json").read_text())
snap = (out / "checkpoint" / "eval_ledger.snap.json").read_bytes()
assert ledger["schema"] == "cdnqual.ledger.v1"
assert ledger["bout_count"] == 6
assert ledger["policy_lambda"] == 3
assert snap == (out / "eval_ledger.json").read_bytes()
rows = [json.loads(l) for l in feat.splitlines() if l.strip()]
by = {r["bout_id"]: r["x"] for r in rows}
assert by["bout_rexmit"][2] >= 1
assert by["bout_ooo"][3] >= 1
assert by["bout_overlap"][4] >= 1
assert digest["feature_row_count"] == 6
print("oracle_selfcheck_ok")
PY
