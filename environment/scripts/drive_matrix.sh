#!/bin/bash
set -euo pipefail
ROOT=/app/environment
WIDE=()
if [[ "${1:-}" == "--wide" ]]; then
  WIDE=(--wide)
fi
bash "$ROOT/scripts/prep_run.sh"
cd "$ROOT"
mkdir -p /app/bin
go build -o /app/bin/hwm_drive ./cmd/hwm_drive
/app/bin/hwm_drive --root "$ROOT" --out /app/output/peak_report.json "${WIDE[@]}"
