#!/usr/bin/env bash
# Phase wrapper: merge only
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
# shellcheck source=/dev/null
source "$ROOT/r9/lattice/merge_q3.sh"
merge_q3 "$@"
