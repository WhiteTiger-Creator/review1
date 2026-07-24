#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
patch -d /app -p0 < fold_build.patch
patch -d /app -p0 < budget_build.patch
patch -d /app -p0 < emit_build.patch
exec bash /app/environment/drive_k4.sh
