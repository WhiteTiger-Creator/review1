#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/exec/build_all.sh"
export APP_ENV_ROOT="${APP_ENV_ROOT:-$ROOT}"
export BEAM_OUT="${BEAM_OUT:-/app/output/span_parity.json}"
export PATH="/app/bin:${PATH}"
rm -f "$BEAM_OUT"
"$ROOT/target/release/w2"
