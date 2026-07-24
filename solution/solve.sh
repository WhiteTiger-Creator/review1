#!/usr/bin/env bash
set -euo pipefail

SOLUTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if patch --dry-run -p1 < "$SOLUTION_DIR/fix.patch" >/dev/null 2>&1; then
    patch -p1 < "$SOLUTION_DIR/fix.patch"
elif patch --dry-run -R -p1 < "$SOLUTION_DIR/fix.patch" >/dev/null 2>&1; then
    echo "Oracle patch is already applied"
else
    echo "Oracle patch does not apply cleanly and is not already applied" >&2
    exit 1
fi

export HOME=/root
export CARGO_HOME=/opt/cargo
export CARGO_NET_OFFLINE=true
export CARGO_TARGET_DIR=/app/target
export PATH=/usr/local/cargo/bin:/usr/bin:/bin

cargo build \
  --release \
  --workspace \
  --locked \
  --offline \
  --manifest-path /app/Cargo.toml

test -x /app/target/release/rstore-cli

rm -f /output/store-inventory.json /output/run-result.json
