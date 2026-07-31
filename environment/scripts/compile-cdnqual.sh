#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH:-/usr/bin}"
cd /app
mkdir -p /app/bin
go build -o /app/bin/cdnqual ./cmd/cdnqual
