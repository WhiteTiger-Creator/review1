#!/bin/bash
set -euo pipefail

ROOT=/app
SRC=/solution/correct

for f in defaults.go load.go filter.go specificity.go manager.go emit.go main.go; do
  if [ ! -f "$SRC/$f" ]; then
    echo "missing oracle source: $SRC/$f" >&2
    exit 1
  fi
done

cp "$SRC/defaults.go" "$ROOT/internal/svcconf/defaults.go"
cp "$SRC/load.go" "$ROOT/internal/svcconf/load.go"
cp "$SRC/filter.go" "$ROOT/internal/walops/filter.go"
cp "$SRC/specificity.go" "$ROOT/internal/clientord/specificity.go"
cp "$SRC/manager.go" "$ROOT/internal/exportacl/manager.go"
cp "$SRC/emit.go" "$ROOT/internal/runtime/emit.go"
cp "$SRC/main.go" "$ROOT/cmd/nfs-acld/main.go"

grep -q 'Base exports.json max_clients_per_export and defaults are authoritative' "$ROOT/internal/svcconf/load.go"
grep -q 'seen\[op.OpID\]' "$ROOT/internal/walops/filter.go"
grep -q 'unicode.IsLetter' "$ROOT/internal/clientord/specificity.go"
grep -A1 'unicode.IsLetter' "$ROOT/internal/clientord/specificity.go" | grep -q 'return 128'
grep -q 'anonUID = m.DefAnonUID' "$ROOT/internal/exportacl/manager.go"
grep -q 'int64(len(clients)) >= m.MaxClients' "$ROOT/internal/exportacl/manager.go"
grep -q 'm.wait = append(m.wait, WaitEntry' "$ROOT/internal/exportacl/manager.go"
grep -q 'm.promote(op.ExportPath)' "$ROOT/internal/exportacl/manager.go"
grep -F 'list[i].Specificity > list[j].Specificity' "$ROOT/internal/exportacl/manager.go"
if grep -q 'CapturedDefaultAccess' "$ROOT/internal/exportacl/manager.go"; then
  echo "manager still uses process-start captured defaults" >&2
  exit 1
fi
if grep -F 'append([]WaitEntry' "$ROOT/internal/exportacl/manager.go"; then
  echo "enqueue still prepends waitlist entries" >&2
  exit 1
fi
if grep -q 'mgr.MaxClients = svcconf.OverlayMaxClients' "$ROOT/cmd/nfs-acld/main.go"; then
  echo "main still realigns manager max clients to overlay after replay" >&2
  exit 1
fi
if grep -q 'OverlayMaxClients' "$ROOT/internal/runtime/emit.go"; then
  echo "runtime emit still realigns max clients with overlay" >&2
  exit 1
fi
if grep -q 'math.Trunc' "$ROOT/internal/runtime/emit.go"; then
  echo "runtime emit still truncates slot_utilization_ratio" >&2
  exit 1
fi
grep -q 'export_metrics.json' "$ROOT/internal/runtime/emit.go"
grep -q 'export_compliance' "$ROOT/internal/runtime/emit.go"
grep -q 'roundHalfAway' "$ROOT/internal/runtime/emit.go"

cd "$ROOT"
mkdir -p /app/bin /app/run
go build -o /app/bin/nfs-acld ./cmd/nfs-acld
/app/bin/nfs-acld /app/config/exports.json

test -f /app/run/export_acls.json
test -f /app/run/export_metrics.json
python3 - <<'PY'
import json
from pathlib import Path
acls = json.loads(Path("/app/run/export_acls.json").read_text())
metrics = json.loads(Path("/app/run/export_metrics.json").read_text())
assert acls["max_clients_per_export"] == 3
assert acls["export_table_id"] == "nfs-east-01"
assert len(acls["exports"]) == 3
assert len(acls["waitlist"]) == 3
assert metrics["journal_applied"] == 30
assert metrics["journal_skipped_dup"] == 1
assert metrics["client_grant_count"] == 8
assert metrics["slot_utilization_ratio"] == 0.8889
assert metrics["export_compliance"] == 94.0
PY

echo "Oracle complete"
