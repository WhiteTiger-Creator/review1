#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

source /app/lib/common.sh
source /app/lib/compare-trees.sh

wait_for_suffix_sync() {
  local base="$1"
  local attempts="${2:-120}"
  local delay="${3:-1}"
  local i provider_csn consumer_csn
  for ((i = 1; i <= attempts; i++)); do
    if trees_equivalent_for_base "${base}"; then
      return 0
    fi
    provider_csn="$(context_csn_for_suffix "${PROVIDER_URI}" "${base}")"
    consumer_csn="$(context_csn_for_suffix "${CONSUMER_URI}" "${base}")"
    if [[ -n "${provider_csn}" && "${provider_csn}" == "${consumer_csn}" ]]; then
      if trees_equivalent_for_base "${base}"; then
        return 0
      fi
    fi
    sleep "${delay}"
  done
  return 1
}

wait_for_sync() {
  wait_for_suffix_sync "${BASE_DN}" "$@"
}
