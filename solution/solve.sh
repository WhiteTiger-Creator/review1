#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d /solution/oracle_src ]; then
  ORACLE_ROOT=/solution/oracle_src
elif [ -d "$SCRIPT_DIR/oracle_src" ]; then
  ORACLE_ROOT="$SCRIPT_DIR/oracle_src"
else
  echo "oracle_src not found (looked in /solution and $SCRIPT_DIR)" >&2
  exit 1
fi

rm -rf /app/src /app/target
cp -r "$ORACLE_ROOT/src" /app/src
cp "$ORACLE_ROOT/Cargo.toml" /app/Cargo.toml
cp "$ORACLE_ROOT/Cargo.lock" /app/Cargo.lock
cp -r "$ORACLE_ROOT/.cargo" /app/.cargo
if [ -d "$ORACLE_ROOT/vendor" ]; then
  rm -rf /app/vendor
  cp -r "$ORACLE_ROOT/vendor" /app/vendor
fi

cd /app
cargo build --release --locked --offline
