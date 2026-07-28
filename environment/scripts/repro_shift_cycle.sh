#!/bin/bash
set -euo pipefail

# Ensure go/gated resolve even when the caller is a login shell that reset PATH.
export PATH="/app/bin:/usr/local/go/bin:${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"

ROOT="${ENV_ROOT:-/app/environment}"
OUT="${OUTPUT_DIR:-/app/output}"
CYCLES="${SHIFT_CYCLES:-2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=init_env.sh
source "${SCRIPT_DIR}/init_env.sh"

mkdir -p "${OUT}"
rm -rf "${OUT:?}"/*
( cd "${ROOT}" && CGO_ENABLED=1 go build -o /app/bin/gated ./cmd/gated && CGO_ENABLED=1 go build -o /app/bin/inspect ./cmd/inspect )
/app/bin/gated -root "${ROOT}" -out "${OUT}" -cycles "${CYCLES}"
