#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

bash oracle_slice.sh
bash oracle_fit.sh
bash oracle_loop.sh

bash /app/environment/scripts/stage_tables.sh
bash /app/environment/scripts/drive_suite.sh
bash /app/environment/scripts/run_scope_chk.sh --suite all --tags strict_mono,relaxed_fast --bundle-out /app/output/residual_scope.json
