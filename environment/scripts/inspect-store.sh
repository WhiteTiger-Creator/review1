#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-/var/lib/mint}"
export CARGO_HOME=/opt/cargo
export PATH="/usr/local/cargo/bin:${PATH}"
cargo run --release -p m07 --quiet -- inspect --root "$ROOT"
