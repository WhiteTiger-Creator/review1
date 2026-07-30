#!/bin/bash
set -euo pipefail
mkdir -p /app/src /app/bin /app/out
cp "$(dirname "$0")/main.go" /app/src/main.go
cd /app/src
/usr/local/go/bin/go build -trimpath -o /app/bin/boys-localization-sweep main.go
