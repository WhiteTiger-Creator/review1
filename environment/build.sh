#!/bin/bash
set -euo pipefail

cd /app/environment

rm -rf build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

test -x ./build/matsqrt
