#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/usr/local/go/bin:${PATH:-}"
mkdir -p /app/bin /app/output
cd "$ROOT"
go build -o /app/bin/trust_desk ./cmd/trust_desk
