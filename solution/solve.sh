#!/bin/bash
# Oracle solve for cpp-quantization-drift-certifier
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES="${ROOT_DIR}/files"

cp "${FILES}/walk/topo_schedule.cpp" /app/walk/topo_schedule.cpp
cp "${FILES}/src/qgraph_loader.cpp" /app/src/qgraph_loader.cpp
cp "${FILES}/catalog/witness_seal.cpp" /app/catalog/witness_seal.cpp
cp "${FILES}/kernel/mx_ops.cpp" /app/kernel/mx_ops.cpp
cp "${FILES}/numeric/wdtype.cpp" /app/numeric/wdtype.cpp
cp "${FILES}/numeric/qstep.cpp" /app/numeric/qstep.cpp
cp "${FILES}/policy/gate_epoch.cpp" /app/policy/gate_epoch.cpp
cp "${FILES}/catalog/json_emit.cpp" /app/catalog/json_emit.cpp

/app/scripts/rebuild-qbound-analyzer.sh
test -x /app/build/qbound-analyzer
/app/build/qbound-analyzer smoke-publish
