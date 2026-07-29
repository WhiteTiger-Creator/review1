#!/usr/bin/env bash
# Sourceable library: defines helpers only; leaves shell-option policy to the caller.

export PROVIDER_URI="${PROVIDER_URI:-ldap://127.0.0.1:1389}"
export CONSUMER_URI="${CONSUMER_URI:-ldap://127.0.0.1:2389}"
export ADMIN_DN="${ADMIN_DN:-cn=admin,dc=example,dc=com}"
export ADMIN_PW="${ADMIN_PW:-adminsecret}"
export REPLICATOR_DN="${REPLICATOR_DN:-cn=replicator,dc=example,dc=com}"
export REPLICATOR_PW="${REPLICATOR_PW:-replicsecret}"
export READER_DN="${READER_DN:-uid=reader,ou=people,dc=example,dc=com}"
export READER_PW="${READER_PW:-readersecret}"
export BASE_DN="${BASE_DN:-dc=example,dc=com}"
export VERIFIER_BASE="${VERIFIER_BASE:-dc=verifier,dc=internal}"
export LDAP_RUNTIME="/app/ldap/runtime"
export PROVIDER_CONF="/app/ldap/provider/slapd.conf"
export CONSUMER_CONF="/app/ldap/consumer/slapd.conf"

ldap_admin() {
  local uri="$1"
  shift
  ldapsearch -x -LLL -H "${uri}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" "$@"
}

ldap_replicator() {
  local uri="$1"
  shift
  ldapsearch -x -LLL -H "${uri}" -D "${REPLICATOR_DN}" -w "${REPLICATOR_PW}" "$@"
}

ldap_reader() {
  local uri="$1"
  shift
  ldapsearch -x -LLL -H "${uri}" -D "${READER_DN}" -w "${READER_PW}" "$@"
}

wait_for_port() {
  local uri="$1"
  local attempts="${2:-60}"
  local delay="${3:-1}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if ldapsearch -x -LLL -H "${uri}" -s base -b "" "(objectClass=*)" namingContexts >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

context_csn_for_suffix() {
  local uri="$1"
  local suffix="$2"
  local output
  output="$(ldap_admin "${uri}" -s base -b "${suffix}" "(objectClass=*)" contextCSN 2>/dev/null || true)"
  awk '/^contextCSN: / { print $2; exit }' <<<"${output}"
}
