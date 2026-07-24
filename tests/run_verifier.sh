#!/usr/bin/env bash
set -euo pipefail

export HOME=/root
export CARGO_HOME=/opt/cargo
export CARGO_NET_OFFLINE=true
export PATH=/usr/local/cargo/bin:/usr/bin:/bin

BUILD_ROOT="$(mktemp -d /tmp/rstore-verifier.XXXXXX)"
cleanup() {
    rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

SRC_DIR="$BUILD_ROOT/src"
TARGET_DIR="$BUILD_ROOT/target"

mkdir -p "$SRC_DIR"
cp -a /tests/verifier-driver/. "$SRC_DIR/"

chmod 0700 "$BUILD_ROOT" "$SRC_DIR"
chown -R root:root "$BUILD_ROOT"

cargo generate-lockfile \
  --offline \
  --manifest-path "$SRC_DIR/Cargo.toml"

CARGO_TARGET_DIR="$TARGET_DIR" \
cargo build \
  --release \
  --locked \
  --offline \
  --manifest-path "$SRC_DIR/Cargo.toml"

VERIFIER_BIN="$TARGET_DIR/release/rstore-verifier"
test -x "$VERIFIER_BIN"

chown root:root /tests
chmod 0700 /tests

exec "$VERIFIER_BIN"
