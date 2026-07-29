#!/bin/bash
set -euo pipefail
/app/environment/ci/build.sh
rm -rf /app/var/model
mkdir -p /app/var/model /app/output
/app/bin/percctl cycle /app/environment/fixtures/suite.json
