#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/state/cache /app/state/policy /output/rt-runs /var/log/rt-daemon
exec "$@"
