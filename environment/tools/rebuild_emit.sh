#!/usr/bin/env bash
set -euo pipefail
cd /app/environment
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target layer_emit yseal -j"$(nproc)"
