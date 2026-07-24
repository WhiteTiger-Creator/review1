#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/build"
mkdir -p "${BUILD}" "${ROOT}/bin"

cmake -S "${ROOT}" -B "${BUILD}" -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD}" --target x7_orch -j"$(nproc)"
cmake --install "${BUILD}" --prefix "${ROOT}"

echo "built ${ROOT}/bin/x7_orch"
