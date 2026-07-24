#!/usr/bin/env bash
set -euo pipefail

cd /app

# Replace vulnerable packages with corrected implementations.
python3 - <<'PY'
from pathlib import Path
import shutil

fixed = Path("/solution/fixed")
if not fixed.exists():
    # Harbor mounts solution at /solution
    candidates = [Path("/tests/../solution/fixed"), Path("/oracle/fixed")]
    for c in candidates:
        if c.exists():
            fixed = c
            break

src_root = Path("/app")
mapping = [
    "internal/canonical/request.go",
    "internal/manifest/store.go",
    "internal/helper/resolve.go",
    "internal/helper/execute.go",
    "internal/dispatch/dispatch.go",
    "internal/recovery/recover.go",
    "internal/reconcile/reconcile.go",
    "internal/cli/commands.go",
]

# Prefer copying the full fixed tree when available.
if fixed.exists():
    for rel in mapping:
        src = fixed / rel
        dst = src_root / rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # Also sync any remaining fixed packages that differ structurally
    for path in fixed.rglob("*.go"):
        rel = path.relative_to(fixed)
        dst = src_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    if (fixed / "go.mod").exists():
        shutil.copy2(fixed / "go.mod", src_root / "go.mod")
else:
    raise SystemExit("fixed sources not found under /solution/fixed")
print("patched sources from solution/fixed")
PY

CGO_ENABLED=0 GOWORK=off GOFLAGS=-mod=readonly go build -o /app/bin/privhelper-bin ./cmd/privhelper
cat > /app/bin/privhelper <<'EOF'
#!/bin/bash
set -euo pipefail
exec "$(dirname "$0")/privhelper-bin" "$@"
EOF
chmod 0755 /app/bin/privhelper /app/bin/privhelper-bin

/app/bin/privhelper reset --scenario ops-seal

# Baseline owner/operator traffic under contamination
/app/bin/privhelper dispatch-batch \
  --fixture /app/fixtures/incident-owner-requests.jsonl \
  --via job \
  --caller-env /app/fixtures/contaminated-caller.conf \
  --trace /app/reports/owner-trace.jsonl

/app/bin/privhelper dispatch-batch \
  --fixture /app/fixtures/incident-operator-requests.jsonl \
  --via direct \
  --caller-env /app/fixtures/contaminated-caller.conf \
  --trace /app/reports/operator-trace.jsonl

# Exact retry
/app/bin/privhelper dispatch \
  --request /app/fixtures/retry-same.json \
  --via direct \
  --trace /app/reports/retry-trace.jsonl
/app/bin/privhelper dispatch \
  --request /app/fixtures/retry-same.json \
  --via direct \
  --trace /app/reports/retry-trace.jsonl

# Conflict on changed body
/app/bin/privhelper dispatch \
  --request /app/fixtures/retry-conflict.json \
  --via job \
  --trace /app/reports/conflict-trace.jsonl || true

# Crash after prepared + recover
REQ=$(mktemp)
cat > "$REQ" <<'JSON'
{"request_id":"oracle-crash-prep","principal":"ops.owner","action":"seal_unit","unit":"oracle-unit"}
JSON
set +e
/app/bin/privhelper dispatch --request "$REQ" --via direct --crash-after prepared
set -e
/app/bin/privhelper recover --trace /app/reports/recover-prep-trace.jsonl

# Crash after effect + recover
REQ2=$(mktemp)
cat > "$REQ2" <<'JSON'
{"request_id":"oracle-crash-effect","principal":"ops.owner","action":"export_bundle","unit":"oracle-unit"}
JSON
set +e
/app/bin/privhelper dispatch --request "$REQ2" --via direct --crash-after effect
set -e
/app/bin/privhelper recover --trace /app/reports/recover-effect-trace.jsonl

# Valid authority rotation (rewrite share helper digests into a gen2 policy tighten)
python3 - <<'PY'
import json, hashlib
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Prefer test support key if mounted; otherwise skip dynamic sign by using
# an already-trusted path through embedded public verification only when key present.
priv_paths = [Path("/tests/support/authority.priv"), Path("/solution/../tests/support/authority.priv")]
priv = None
for p in priv_paths:
    if p.exists():
        priv = Ed25519PrivateKey.from_private_bytes(p.read_bytes())
        break
base = json.loads(Path("/app/share/privhelper/authority-manifest-v1.json").read_text())
man = {
    "scenario": "ops-seal",
    "generation": 2,
    "policy": {
        "ops.owner": ["seal_unit", "export_bundle", "rotate_token"],
        "ops.operator": ["seal_unit"],
    },
    "helpers": base["helpers"],
}
raw = (json.dumps(man, indent=2) + "\n").encode()
out_m = Path("/tmp/oracle-man-v2.json")
out_s = Path("/tmp/oracle-man-v2.sig")
out_m.write_bytes(raw)
if priv is None:
    raise SystemExit("signing key unavailable for oracle rotation exercise")
out_s.write_bytes(priv.sign(raw))
print(out_m)
print(out_s)
PY
/app/bin/privhelper manifest-install --manifest /tmp/oracle-man-v2.json --signature /tmp/oracle-man-v2.sig

/app/bin/privhelper selftest --mode security

/app/bin/privhelper reconcile \
  --trace /app/reports/reconcile-trace.jsonl \
  --output /app/reports/authority-report.json

python3 - <<'PY'
import json, hashlib
from pathlib import Path

rep = json.loads(Path("/app/reports/authority-report.json").read_text())
assert rep["scenario"] == "ops-seal"
assert isinstance(rep["violations"], list)
assert rep["helpers_trusted"] is True
assert len(rep["ledger_digest"]) == 64

def load(path, key):
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get(key, 0))
    return rows

payload = {
    "decisions": load("/app/var/privhelper/decisions.jsonl", "seq"),
    "effects": load("/app/var/privhelper/effects.jsonl", "seq"),
    "journal": load("/app/var/privhelper/journal.jsonl", "event_seq"),
}
digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
assert rep["ledger_digest"] == digest
print("oracle reconcile validation ok")
PY
