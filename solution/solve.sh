#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:${PATH:-}"
export CARGO_INCREMENTAL=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORACLE_SRC="${SCRIPT_DIR}/oracle_src"

cp "${ORACLE_SRC}/Cargo.toml" /app/Cargo.toml
cp -r "${ORACLE_SRC}/.cargo" /app/
cp -r "${ORACLE_SRC}/src/"* /app/src/

if [ -d "${ORACLE_SRC}/vendor" ]; then
  rm -rf /app/vendor
  cp -r "${ORACLE_SRC}/vendor" /app/
fi
if [ -f "${ORACLE_SRC}/Cargo.lock" ]; then
  cp "${ORACLE_SRC}/Cargo.lock" /app/Cargo.lock
fi

cd /app
cargo build --release --locked --offline
