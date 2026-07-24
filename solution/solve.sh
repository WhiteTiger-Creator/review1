#!/bin/bash
set -euo pipefail

cd /app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cp "${SCRIPT_DIR}/impl/inc/"* /app/inc/
cp "${SCRIPT_DIR}/impl/src/"* /app/src/
cp "${SCRIPT_DIR}/impl/Makefile" /app/Makefile

make clean && make
./bin/tuf-rollout-verifier
