#!/bin/bash
set -euo pipefail
cd /app/environment
make clean
make -j"$(nproc)"
make install
