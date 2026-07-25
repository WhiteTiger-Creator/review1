#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PATH="/usr/local/cargo/bin:${PATH:-/usr/bin}"
export CARGO_NET_OFFLINE=true
export CARGO_HOME="${CARGO_HOME:-$ROOT/.cargo-home}"
mkdir -p "$ROOT/libexec" "$CARGO_HOME"
cargo build --release --locked --offline
install -m 0755 "$ROOT/target/release/modal-reconciler" "$ROOT/libexec/modal-reconciler"
"$ROOT/libexec/modal-reconciler" --help >/dev/null
"$ROOT/libexec/modal-reconciler" spectrum --model "$ROOT/examples/bridge-model.json" >/dev/null
