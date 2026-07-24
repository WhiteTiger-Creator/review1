#!/bin/bash
set -euo pipefail

ENV="/app/environment"
BIN="/app/bin/q7"

if [[ ! -x "$BIN" ]]; then
  make -C "$ENV" clean all
fi

exec "$BIN" "$@"
