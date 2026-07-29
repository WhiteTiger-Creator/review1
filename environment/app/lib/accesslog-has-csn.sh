#!/usr/bin/env bash
set -euo pipefail

source /app/lib/common.sh

cookie_csn="$1"
if [[ -z "${cookie_csn}" ]]; then
  exit 1
fi

if ldapsearch -x -LLL -H "${PROVIDER_URI}" -D "${REPLICATOR_DN}" -w "${REPLICATOR_PW}" \
  -b "cn=accesslog" "(entryCSN=${cookie_csn})" dn 2>/dev/null | grep -q '^dn:'; then
  exit 0
fi

if ldapsearch -x -LLL -H "${PROVIDER_URI}" -D "${REPLICATOR_DN}" -w "${REPLICATOR_PW}" \
  -b "cn=accesslog" "(reqMod=*${cookie_csn}*)" reqMod 2>/dev/null | grep -Fq "${cookie_csn}"; then
  exit 0
fi

exit 1
