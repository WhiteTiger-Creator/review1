#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

source /app/lib/common.sh

normalize_tree() {
  local uri="$1"
  local base="$2"
  local output
  output="$(ldap_admin "${uri}" -b "${base}" "(objectClass=*)" dn objectClass cn uid mail sn description member 2>/dev/null || true)"
  if [[ -z "${output}" ]]; then
    return 0
  fi
  printf '%s\n' "${output}" | awk '
      /^dn: / { flush(); entry=$0; n=0; next }
      /^[a-zA-Z]/ { attrs[++n]=$0 }
      END { flush() }
      function flush() {
        if (entry == "") return
        if (n > 0) {
          for (i = 1; i <= n; i++) {
            for (j = i + 1; j <= n; j++) {
              if (attrs[i] > attrs[j]) {
                tmp = attrs[i]
                attrs[i] = attrs[j]
                attrs[j] = tmp
              }
            }
          }
          block = entry
          for (i = 1; i <= n; i++) {
            block = block "\n" attrs[i]
          }
          print block
        } else {
          print entry
        }
        entry = ""
        n = 0
      }
    ' | LC_ALL=C sort
}

trees_equivalent_for_base() {
  local base="$1"
  local left right
  local provider_count consumer_count
  wait_for_port "${PROVIDER_URI}" 1 1 || return 1
  wait_for_port "${CONSUMER_URI}" 1 1 || return 1
  provider_count="$(entry_count "${PROVIDER_URI}" "${base}")"
  if [[ "${provider_count}" -lt 1 ]]; then
    return 1
  fi
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
  ldap_admin "${uri}" -b "${base}" "(objectClass=*)" dn 2>/dev/null \
    | awk '/^dn: / { c++ } END { print c+0 }'
}
