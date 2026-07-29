#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

source /app/lib/common.sh
source /app/lib/compare-trees.sh

wait_for_suffix_sync() {
  local base="$1"
  local attempts="${2:-80}"
  local delay="${3:-0.25}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if trees_equivalent_for_base "${base}"; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

wait_for_sync() {
  wait_for_suffix_sync "${BASE_DN}" "$@"
}
