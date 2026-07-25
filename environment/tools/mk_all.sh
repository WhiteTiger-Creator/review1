#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p /app/bin
cd "$ROOT"
go build -o /app/bin/gm_infer ./cmd/gm_infer
