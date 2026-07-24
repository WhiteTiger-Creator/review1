#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-/app/output/stage}"
rm -rf "${TARGET}"
mkdir -p "${TARGET}"
rm -f /app/output/final.h5 /app/output/run-record.json
