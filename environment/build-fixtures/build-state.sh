#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PROVIDER_URI="ldap://127.0.0.1:1389"
export CONSUMER_URI="ldap://127.0.0.1:2389"
export ADMIN_DN="cn=admin,dc=example,dc=com"
export ADMIN_PW="adminsecret"
export BASE_DN="dc=example,dc=com"
export VERIFIER_BASE="dc=verifier,dc=internal"

ROOT="/opt/build-fixtures"
APP="/app"
GOOD="${ROOT}/configs/good"

source "${APP}/lib/common.sh"

install -d -m 0755 "${APP}/ldap/runtime" "${APP}/ldap/provider/data" "${APP}/ldap/provider/accesslog" \
  "${APP}/ldap/provider/verifier-data" "${APP}/ldap/consumer/data" "${APP}/ldap/consumer/verifier-data" \
  "${APP}/backups" /output

install -m 0644 "${GOOD}/provider/acl.conf" "${APP}/config/provider/acl.conf"
install -m 0644 "${GOOD}/provider/slapd.conf.in" "${APP}/config/provider/slapd.conf.in"
install -m 0644 "${GOOD}/consumer/slapd.conf.in" "${APP}/config/consumer/slapd.conf.in"
install -m 0644 "${GOOD}/provider/server-id" "${APP}/config/provider/server-id"
install -m 0644 "${GOOD}/consumer/server-id" "${APP}/config/consumer/server-id"

render() {
  local role="$1"
  local sid
  sid="$(tr -d '[:space:]' <"${GOOD}/${role}/server-id")"
  sed "s/@SERVER_ID@/${sid}/g" "${APP}/config/${role}/slapd.conf.in" >"${APP}/ldap/${role}/slapd.conf"
}

render provider
render consumer

chown -R openldap:openldap "${APP}/ldap"

start_slapd() {
  local role="$1"
  local uri="$2"
  slapd -f "${APP}/ldap/${role}/slapd.conf" -h "${uri}" -u openldap -g openldap
  wait_for_port "${uri}" 90 1
}

stop_slapd() {
  local role="$1"
  local pidfile="${APP}/ldap/runtime/${role}.pid"
  if [[ -f "${pidfile}" ]]; then
    kill "$(cat "${pidfile}")" || true
    sleep 2
  fi
}

start_slapd provider "${PROVIDER_URI}"
ldapadd -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" -f "${APP}/seed/base.ldif"
ldapadd -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" -f "${APP}/seed/verifier-base.ldif"

start_slapd consumer "${CONSUMER_URI}"

source "${APP}/lib/wait-sync.sh"
wait_for_sync 180 1

ldapmodify -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" <<'EOF'
dn: uid=carol,ou=people,dc=example,dc=com
changetype: add
objectClass: inetOrgPerson
cn: Carol Example
sn: Example
uid: carol
mail: carol@example.com
description: incremental add
EOF

ldapmodify -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" <<'EOF'
dn: uid=bob,ou=people,dc=example,dc=com
changetype: modrdn
newrdn: uid=robert
deleteoldrdn: 1

dn: uid=robert,ou=people,dc=example,dc=com
changetype: modify
replace: mail
mail: robert@example.com
EOF

wait_for_sync 180 1

stale_dir="$(mktemp -d)"
mkdir -p "${stale_dir}/meta"
cp -a "${APP}/ldap/consumer/data" "${stale_dir}/"
cp -a "${APP}/ldap/consumer/verifier-data" "${stale_dir}/"
context_csn_for_suffix "${CONSUMER_URI}" "${BASE_DN}" >"${stale_dir}/meta/context-csn"

ldapmodify -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" <<'EOF'
dn: uid=alice,ou=people,dc=example,dc=com
changetype: delete
EOF

ldapmodify -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" <<'EOF'
dn: uid=robert,ou=people,dc=example,dc=com
changetype: modrdn
newrdn: uid=bob
deleteoldrdn: 1
EOF

wait_for_sync 180 1

# Simulate access-log trimming that invalidates the saved cookie.
ldapsearch -x -LLL -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" \
  -b "cn=accesslog" "(objectClass=*)" dn \
  | awk '/^dn: / { print $2 }' \
  | while read -r logdn; do
      ldapdelete -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" "${logdn}" || true
    done

# Delta-syncrepl persist requires accesslog entries from the live context CSN onward.
ldapmodify -x -H "${PROVIDER_URI}" -D "${ADMIN_DN}" -w "${ADMIN_PW}" <<'EOF'
dn: dc=example,dc=com
changetype: modify
replace: description
description: accesslog reseeded after trim
EOF

tar -C "${stale_dir}" -cf "${APP}/backups/consumer-state.tar" data verifier-data meta
rm -rf "${stale_dir}"

stop_slapd consumer
stop_slapd provider

rm -rf "${APP}/ldap/consumer/data" "${APP}/ldap/consumer/verifier-data"
mkdir -p "${APP}/ldap/consumer/data" "${APP}/ldap/consumer/verifier-data"
chown -R openldap:openldap "${APP}/ldap/consumer"

# Install agent-facing runtime configs for the shipped image.
install -m 0644 "${ROOT}/configs/broken/provider/acl.conf" "${APP}/config/provider/acl.conf"
install -m 0644 "${ROOT}/configs/broken/provider/slapd.conf.in" "${APP}/config/provider/slapd.conf.in"
install -m 0644 "${GOOD}/consumer/slapd.conf.in" "${APP}/config/consumer/slapd.conf.in"
rm -f "${APP}/config/provider/server-id" "${APP}/config/consumer/server-id"

chown -R root:root "${APP}/backups"
chmod -R a-w "${APP}/backups"
find "${APP}/backups" -type d -exec chmod 555 {} +
find "${APP}/backups" -type f -exec chmod 444 {} +
