#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

source /app/lib/common.sh

normalize_tree() {
  local uri="$1"
  local base="$2"
  ldap_admin "${uri}" -b "${base}" "(objectClass=*)" dn objectClass cn uid mail sn description member \
    | awk '
      /^dn: / { if (entry != "") print entry; entry=$0; next }
      /^[a-zA-Z]/ { if (entry != "") entry=entry "\n" $0 }
      END { if (entry != "") print entry }
    ' \
    | LC_ALL=C sort
}

trees_equivalent_for_base() {
  local base="$1"
  local left right
  left="$(mktemp)"
  right="$(mktemp)"
  normalize_tree "${PROVIDER_URI}" "${base}" >"${left}"
  normalize_tree "${CONSUMER_URI}" "${base}" >"${right}"
  if diff -q "${left}" "${right}" >/dev/null 2>&1; then
    rm -f "${left}" "${right}"
    return 0
  fi
  rm -f "${left}" "${right}"
  return 1
}

trees_equivalent() {
  trees_equivalent_for_base "${BASE_DN}"
}

verifier_trees_equivalent() {
  trees_equivalent_for_base "${VERIFIER_BASE}"
}

entry_count() {
  local uri="$1"
  local base="$2"
  ldap_admin "${uri}" -b "${base}" "(objectClass=*)" dn \
    | awk '/^dn: / { c++ } END { print c+0 }'
}
