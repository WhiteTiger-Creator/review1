#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash ./fix_briar.sh
bash ./fix_flume.sh
bash ./fix_kerf.sh
chmod +x /app/environment/scripts/compile_lane.sh
/app/environment/scripts/compile_lane.sh
mkdir -p /app/output
exec /app/environment/tools/rivet_gate \
  --pack /app/environment/fixtures/ax025_pack \
  --db /app/output/shift_ledger.db \
  --bundle-out /app/output/evidence_bundle.tar
