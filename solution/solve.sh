#!/bin/bash
# Reference solution: install the recovered strategy as /app/strategy.js.
set -euo pipefail

cd /app
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$DIR/strategy.js" /app/strategy.js
echo "gauntlet reference strategy installed at /app/strategy.js"
