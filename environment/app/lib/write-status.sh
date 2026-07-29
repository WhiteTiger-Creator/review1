#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

source /app/lib/common.sh
source /app/lib/compare-trees.sh

write_replication_status() {
  local output="${1:-/output/replication-status.json}"
  local recovery_mode="${2:-none}"
  local equivalent="false"
  if trees_equivalent; then
    equivalent="true"
  fi
  mkdir -p "$(dirname "${output}")"
  cat >"${output}" <<EOF
{
  "provider_uri": "${PROVIDER_URI}",
  "consumer_uri": "${CONSUMER_URI}",
  "equivalent": ${equivalent},
  "provider_entry_count": $(entry_count "${PROVIDER_URI}" "${BASE_DN}"),
  "consumer_entry_count": $(entry_count "${CONSUMER_URI}" "${BASE_DN}"),
  "provider_context_csn": "$(context_csn_for_suffix "${PROVIDER_URI}" "${BASE_DN}")",
  "consumer_context_csn": "$(context_csn_for_suffix "${CONSUMER_URI}" "${BASE_DN}")",
  "recovery_mode": "${recovery_mode}",
  "checked_at": $(date +%s)
}
EOF
}
