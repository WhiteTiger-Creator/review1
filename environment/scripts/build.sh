#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin"

rm -rf /app/build
cd /app
cmake -S /app -B /app/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /app/build --target emsolve -j"${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
mkdir -p /app/bin
cp /app/build/emsolve/emsolve /app/bin/emsolve
