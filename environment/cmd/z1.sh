#!/usr/bin/env bash
# Phase wrapper: bind only
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
# shellcheck source=/dev/null
source "$ROOT/n4/harbor/op_k7.sh"
op_k7 "$@"
