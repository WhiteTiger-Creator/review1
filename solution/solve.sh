#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH="${SCRIPT_DIR}/cpf-fold-trace.patch"
cd /loadcrest
if patch -p1 --dry-run <"${PATCH}" >/dev/null 2>&1; then
  patch -p1 <"${PATCH}"
elif patch -p1 -R --dry-run <"${PATCH}" >/dev/null 2>&1; then
  echo "patch already applied"
else
  echo "patch does not apply in either direction" >&2
  exit 1
fi
/loadcrest/build-fold-map.sh
