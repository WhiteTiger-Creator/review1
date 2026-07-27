#!/usr/bin/env bash
set -euo pipefail

LISTEN="${VAULTD_LISTEN:-127.0.0.1:9470}"
CONFIG="${KSEAL_CONFIG:-/app/config/service.toml}"

exec /app/bin/opsd --listen "$LISTEN" --config "$CONFIG"
