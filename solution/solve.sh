#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

patch --batch --forward -p1 -d /app < "$SCRIPT_DIR/delegated-authority-closure.patch"

cd /app
export CARGO_NET_OFFLINE=true
cargo build --workspace --release --locked --offline

bash /app/scripts/check-admission.sh
