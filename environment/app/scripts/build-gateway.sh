#!/usr/bin/env bash
set -euo pipefail
cd /app
cargo build --workspace --release --locked --offline
