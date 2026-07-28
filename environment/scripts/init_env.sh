#!/bin/bash
set -euo pipefail

# Login shells (e.g. tmux) reset PATH via /etc/profile; keep toolchain reachable.
export PATH="/app/bin:/usr/local/go/bin:${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"

ROOT="${ENV_ROOT:-/app/environment}"
STATE="${ROOT}/state"
OUT="${OUTPUT_DIR:-/app/output}"

mkdir -p "${STATE}" "${OUT}"
rm -f "${STATE}"/*.sock 2>/dev/null || true

if [[ ! -x /app/bin/gated ]]; then
  echo "gated binary missing; build via image or go build" >&2
  exit 1
fi
