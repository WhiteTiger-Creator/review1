#!/bin/sh
set -eu

PIP_BIN="$1"
LOCK_FILE="$2"

"$PIP_BIN" install --no-cache-dir --require-hashes -r "$LOCK_FILE"

