#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cp "${ROOT}/engraver_overlay/"*.vala /app/engraver/
make -C /app clean
make -C /app engrave PARCELS=/app/parcels OUT=/app/out
test -f /app/out/crate.index
test -f /app/out/seal.manifest
