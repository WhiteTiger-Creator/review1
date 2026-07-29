#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

cargo build --workspace --release --locked --offline

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
mkdir -p "$OUT"

"$ROOT/target/release/admission-gateway" evaluate \
    --request /app/requests/release.json \
    --output "$OUT"

"$ROOT/target/release/admission-gateway" inspect --request /app/requests/release.json
"$ROOT/target/release/admission-gateway" inspect --evidence "$OUT/evidence.cbor"
"$ROOT/target/release/admission-gateway" verify \
    --request /app/requests/release.json \
    --decision "$OUT/decision.json" \
    --evidence "$OUT/evidence.cbor"

DECISION="$(jq -r .decision "$OUT/decision.json")"
test "$DECISION" = "approve"
EVIDENCE_DIGEST="$(jq -r .evidence_digest "$OUT/decision.json")"
COMPUTED="$(python3 - "$OUT/evidence.cbor" <<'PY'
import hashlib, pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
print("sha256:" + hashlib.sha256(data).hexdigest())
PY
)"
test "$EVIDENCE_DIGEST" = "$COMPUTED"

PERM_ROOT="$(mktemp -d)"
trap 'rm -rf "$OUT" "$PERM_ROOT"' EXIT
cp -a "$ROOT" "$PERM_ROOT/workspace"
WORK="$PERM_ROOT/workspace"
OUT2="$PERM_ROOT/out2"
mkdir -p "$OUT2"

python3 - <<'PY' "$WORK"
import json, pathlib, random, sys
root = pathlib.Path(sys.argv[1])
req_path = root / "requests" / "release.json"
req = json.loads(req_path.read_text())
random.seed(17)
req["envelopes"] = sorted(req["envelopes"], key=lambda p: random.random())
req_path.write_text(json.dumps(req, indent=2) + "\n")
graph_path = root / "config" / "artifact-graph.json"
graph = json.loads(graph_path.read_text())
graph["edges"] = list(reversed(graph["edges"]))
graph_path.write_text(json.dumps(graph, indent=2) + "\n")
PY

"$WORK/target/release/admission-gateway" evaluate \
    --request "$WORK/requests/release.json" \
    --output "$OUT2"

cmp -s "$OUT/decision.json" "$OUT2/decision.json"
cmp -s "$OUT/evidence.cbor" "$OUT2/evidence.cbor"

BASELINE="$(mktemp -d)"
mkdir -p "$BASELINE"
"$ROOT/target/release/admission-gateway" evaluate \
    --request /app/requests/release.json \
    --output "$BASELINE" || true
if [ -f "$BASELINE/decision.json" ]; then
  REJECT_OUT="$PERM_ROOT/reject-out"
  mkdir -p "$REJECT_OUT"
  cp -a "$BASELINE/." "$REJECT_OUT/"
  BEFORE_DEC="$(sha256sum "$REJECT_OUT/decision.json" | awk '{print $1}')"
  BEFORE_EV="$(sha256sum "$REJECT_OUT/evidence.cbor" | awk '{print $1}')"
  BAD_REQ="$PERM_ROOT/bad-request.json"
  python3 - <<'PY' "$BAD_REQ"
import json, pathlib, sys
src = json.loads(pathlib.Path("/app/requests/release.json").read_text())
src["evaluation_epoch"] = 1
pathlib.Path(sys.argv[1]).write_text(json.dumps(src, indent=2) + "\n")
PY
  set +e
  "$ROOT/target/release/admission-gateway" evaluate --request "$BAD_REQ" --output "$REJECT_OUT"
  RC=$?
  set -e
  test "$RC" -ne 0
  AFTER_DEC="$(sha256sum "$REJECT_OUT/decision.json" | awk '{print $1}')"
  AFTER_EV="$(sha256sum "$REJECT_OUT/evidence.cbor" | awk '{print $1}')"
  test "$BEFORE_DEC" = "$AFTER_DEC"
  test "$BEFORE_EV" = "$AFTER_EV"
fi

echo "[check-admission] ok"
