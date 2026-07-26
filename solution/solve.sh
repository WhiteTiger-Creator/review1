#!/usr/bin/env bash
set -euo pipefail
cp /solution/main.go /app/environment/main.go
cd /app/environment
GO_BIN="${GO_BIN:-/usr/local/go/bin/go}"
"$GO_BIN" build -o /tmp/lease_sim .
