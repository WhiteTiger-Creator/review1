#!/bin/bash
set -euo pipefail

cd /app/environment

cp /solution/src/matsqrt_impl.cpp src/matsqrt_impl.cpp

rm -rf build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

test -x ./build/matsqrt || {
    echo "solve.sh: build did not produce ./build/matsqrt" >&2
    exit 1
}

./build/matsqrt data/case_spd_n5_c6.txt /tmp/matsqrt_smoke.out || {
    echo "solve.sh: matsqrt failed on case_spd_n5_c6.txt" >&2
    exit 1
}

echo "solve.sh: build succeeded"
