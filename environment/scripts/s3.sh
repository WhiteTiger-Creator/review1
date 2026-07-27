#!/usr/bin/env bash
# Documented rewind path
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
SCR="$ROOT/scratch"
rm -f "$SCR/durable.bad"
rm -rf "$SCR/warm"
find /app/output -name '*.cache' -delete 2>/dev/null || true
rm -f "$SCR"/run_*.json
echo "rewind: cleared durable.bad and warm caches"
