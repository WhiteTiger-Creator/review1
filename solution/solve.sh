#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app
patch -p1 < "$ROOT_DIR/patches/all-fixes.patch"

mkdir -p /app/environment/tools
cd /app/environment
CGO_ENABLED=0 go build -o /app/environment/tools/drvx ./cmd/drvx
