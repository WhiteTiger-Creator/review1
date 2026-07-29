#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

patch -p0 -d /app/environment < "$ROOT_DIR/dm7_seg.go.patch"
patch -p0 -d /app/environment < "$ROOT_DIR/pk3_gate.go.patch"
patch -p0 -d /app/environment < "$ROOT_DIR/an8_bear.go.patch"
patch -p0 -d /app/environment < "$ROOT_DIR/rs5_resume.go.patch"

make -C /app/environment build install
