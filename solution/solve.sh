#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/repair-lock.js" /app/bin/repair-lock.js
chmod +x /app/bin/repair-lock.js
node /app/bin/repair-lock.js
