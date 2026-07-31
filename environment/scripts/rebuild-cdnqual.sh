#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH:-/usr/bin}"
cd /app
bash /app/scripts/compile-cdnqual.sh
