#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p /app/bin /app/output
cd "$ROOT"
cargo build --release -p w2
(cd "$ROOT/q7" && go build -o /app/bin/xq7 ./cmd/xq7)
