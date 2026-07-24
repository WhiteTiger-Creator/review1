#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/bin
cd /app
rm -rf /app/bin/vaultquorum
go build -trimpath -o /app/bin/vaultquorum .
