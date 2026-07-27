#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
OVERLAY="${ROOT}/overlay"

cp "${OVERLAY}/Makefile" /app/Makefile
rm -rf /app/src
mkdir -p /app/src
cp -R "${OVERLAY}/src/." /app/src/

make -C /app clean
make -C /app install
