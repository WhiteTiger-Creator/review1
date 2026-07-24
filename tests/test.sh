#!/usr/bin/env bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
    echo "Error: no working directory is configured" >&2
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

export HOME=/root
export CARGO_HOME=/opt/cargo
export CARGO_NET_OFFLINE=true
export PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:/usr/bin:/bin"

CONTRACT_BUILD_ROOT="$(mktemp -d /tmp/rstore-contract.XXXXXX)"
cleanup_contract_build() {
    rm -rf "$CONTRACT_BUILD_ROOT"
}
trap cleanup_contract_build EXIT

CONTRACT_SRC="$CONTRACT_BUILD_ROOT/src"
CONTRACT_TARGET="$CONTRACT_BUILD_ROOT/target"
mkdir -p "$CONTRACT_SRC"
cp -a /tests/verifier-driver/. "$CONTRACT_SRC/"

cargo generate-lockfile \
  --offline \
  --manifest-path "$CONTRACT_SRC/Cargo.toml"

CARGO_TARGET_DIR="$CONTRACT_TARGET" \
cargo build \
  --release \
  --locked \
  --offline \
  --manifest-path "$CONTRACT_SRC/Cargo.toml"

CONTRACT_VERIFIER="$CONTRACT_TARGET/release/rstore-verifier"
test -x "$CONTRACT_VERIFIER"

if [ ! -f /output/store-inventory.json ] || [ ! -f /output/run-result.json ]; then
    /app/scripts/reset-visible-store.sh /var/lib/mint
    "$CONTRACT_VERIFIER" materialize 1 /var/lib/mint
    /app/target/release/rstore-cli recover --root /var/lib/mint --output /output/store-inventory.json
    /app/target/release/rstore-cli run-image --root /var/lib/mint --image demo --result /output/run-result.json
fi

cd /tests
export PYTHONSAFEPATH=1

PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:${PATH}" \
/opt/verifier-venv/bin/pytest \
    --rootdir=/tests \
    --confcutdir=/tests \
    --ctrf /logs/verifier/ctrf.json \
    /tests/test_outputs.py \
    -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
