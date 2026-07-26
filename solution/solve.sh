#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
patch -p0 -d /app < gm_infer.patch
rm -f /app/environment/var/ledger.jsonl /app/environment/var/snapshot.json /app/environment/var/shadow.json
bash /app/environment/tools/mk_all.sh
