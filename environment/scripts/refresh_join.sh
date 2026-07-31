#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
cargo build --release --bin skew_probe
cp -f "$ROOT/target/release/skew_probe" "$ROOT/tools/skew_probe/skew_probe"
chmod +x "$ROOT/tools/skew_probe/skew_probe"
