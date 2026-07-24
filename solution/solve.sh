#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app
patch -p1 --forward --batch < "${ROOT_DIR}/aurora-fix.patch"
chmod +x /app/aurora-build.mjs

rm -rf /output/oracle-check /output/oracle-legacy
mkdir -p /output/oracle-check /output/oracle-legacy

node /app/aurora-build.mjs synthesize \
  --inventory /data/cases/current/inventory.json \
  --profiles /data/cases/current/profiles.yaml \
  --output-dir /output/oracle-check

node /app/aurora-build.mjs synthesize \
  --inventory /data/cases/legacy/inventory.json \
  --profiles /data/cases/legacy/profiles-v1.json \
  --output-dir /output/oracle-legacy

make -n -f /output/oracle-check/ffmpeg.mk all ASSET_ROOT=/data/assets
