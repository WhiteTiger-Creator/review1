#!/usr/bin/env bash
# Oracle solve - task identity wind-tunnel-aero-coefficient-validator token cf44875e
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app
patch -p1 < "${ROOT_DIR}/patches/qinf.patch"
patch -p1 < "${ROOT_DIR}/patches/tapcp.patch"
patch -p1 < "${ROOT_DIR}/patches/panel.patch"
patch -p1 < "${ROOT_DIR}/patches/mref.patch"
patch -p1 < "${ROOT_DIR}/patches/zeros.patch"
patch -p1 < "${ROOT_DIR}/patches/loadcell.patch"
patch -p1 < "${ROOT_DIR}/patches/errband.patch"
patch -p1 < "${ROOT_DIR}/patches/batch_stage.patch"
patch -p1 < "${ROOT_DIR}/patches/cli.patch"
make build
test -x /usr/local/bin/wtac-validate
echo "solve.sh: oracle applied"
