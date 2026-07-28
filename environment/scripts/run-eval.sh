#!/usr/bin/env bash
set -euo pipefail
exec env PYTHONPATH=/app /app/binx/hwml eval "$@"
