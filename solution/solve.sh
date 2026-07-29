#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

install -d /app/config/provider /app/config/consumer /app/lib

printf '%s\n' '1' > /app/config/provider/server-id
printf '%s\n' '2' > /app/config/consumer/server-id
install -m 0644 fixed/config/provider/slapd.conf.in /app/config/provider/slapd.conf.in
install -m 0644 fixed/config/provider/acl.conf /app/config/provider/acl.conf
install -m 0644 fixed/config/consumer/slapd.conf.in /app/config/consumer/slapd.conf.in
install -m 0755 fixed/bin/start-ldap /app/bin/start-ldap
install -m 0755 fixed/bin/stop-ldap /app/bin/stop-ldap
install -m 0755 fixed/bin/restore-consumer /app/bin/restore-consumer
install -m 0755 fixed/bin/check-replica /app/bin/check-replica
install -m 0755 fixed/lib/compare-trees.sh /app/lib/compare-trees.sh
install -m 0755 fixed/lib/wait-sync.sh /app/lib/wait-sync.sh

source /app/lib/common.sh
source /app/lib/wait-sync.sh

/app/bin/stop-ldap 2>/dev/null || true
/app/bin/start-ldap
wait_for_sync 80 0.25
/app/bin/check-replica --report /output/replication-status.json

/app/bin/stop-ldap
/app/bin/start-ldap
wait_for_sync 80 0.25
/app/bin/restore-consumer /app/backups/consumer-state.tar
/app/bin/check-replica --report /output/replication-status.json
/app/bin/stop-ldap
