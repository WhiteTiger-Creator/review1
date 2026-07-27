#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:/usr/local/bin:/app/bin:${PATH}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app
patch -p0 < "${ROOT_DIR}/oracle.patch"
cargo build --release --locked --offline
cp /app/target/release/opsctl /app/bin/opsctl
cp /app/target/release/opsd /app/bin/opsd
