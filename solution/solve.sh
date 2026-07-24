#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="${SCRIPT_DIR}/modal-stiffness-calibration.patch"
cd /opt/spanforge

if patch -p1 --dry-run < "$PATCH" >/dev/null 2>&1; then
  patch -p1 < "$PATCH"
elif patch -p1 -R --dry-run < "$PATCH" >/dev/null 2>&1; then
  echo "patch already applied"
else
  echo "patch applies in neither direction" >&2
  exit 1
fi

/opt/spanforge/build-modal-reconciler.sh
