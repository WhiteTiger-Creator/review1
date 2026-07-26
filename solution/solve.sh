#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHES="${SCRIPT_DIR}/files"

cp "${PATCHES}/fyop/occupancy/guard.py" "${APP_ROOT}/fyop/occupancy/guard.py"
cp "${PATCHES}/fyop/staging/ingest.py" "${APP_ROOT}/fyop/staging/ingest.py"
cp "${PATCHES}/fyop/staging/jsonutil.py" "${APP_ROOT}/fyop/staging/jsonutil.py"
cp "${PATCHES}/fyop/trajectory/solver.py" "${APP_ROOT}/fyop/trajectory/solver.py"
cp "${PATCHES}/fyop/residual/reach.py" "${APP_ROOT}/fyop/residual/reach.py"
cp "${PATCHES}/fyop/residual/physics_gate.py" "${APP_ROOT}/fyop/residual/physics_gate.py"
cp "${PATCHES}/fyop/export/atlas.py" "${APP_ROOT}/fyop/export/atlas.py"
cp "${PATCHES}/fyop/cli.py" "${APP_ROOT}/fyop/cli.py"

bash "${APP_ROOT}/scripts/build.sh"
mkdir -p "${APP_ROOT}/output" "${APP_ROOT}/state"
