#!/usr/bin/env bash
# Phase wrapper: remount recompute only
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
# shellcheck source=/dev/null
source "$ROOT/w2/vapor/recalc_v2.sh"
recalc_v2 "$@"
