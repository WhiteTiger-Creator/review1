#!/bin/bash
# Offline Go build only; modules are already in the image (no module download).
set -euo pipefail
export HOME="${HOME:-/tmp}"
if [ ! -d "$HOME" ] || [ ! -w "$HOME" ]; then
  export HOME=/tmp
fi
export GOCACHE="${GOCACHE:-/tmp/go-cache}"
export GOTOOLCHAIN=local
export CGO_ENABLED=0
mkdir -p /app/bin "$GOCACHE"
cd /app/environment
go build -mod=readonly -o /app/bin/cqrun ./cmd/cqrun
