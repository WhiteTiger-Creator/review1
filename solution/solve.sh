#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:/usr/local/bin:/app/bin:${PATH}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

PATCH="${ROOT_DIR}/oracle.patch"
if patch --dry-run -p1 < "$PATCH" >/dev/null 2>&1; then
    patch -p1 < "$PATCH"
elif patch --reverse --dry-run -p1 < "$PATCH" >/dev/null 2>&1; then
    echo "Oracle patch is already applied"
else
    echo "Oracle patch does not apply cleanly to the current source tree" >&2
    exit 1
fi

cargo build --release --locked --offline
cp /app/target/release/opsctl /app/bin/opsctl
cp /app/target/release/opsd /app/bin/opsd
chmod -R a+rwX /app/target /app/bin /app/state 2>/dev/null || true
