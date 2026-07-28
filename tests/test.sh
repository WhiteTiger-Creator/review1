#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

rc=1
trap 'exit "$rc"' EXIT

fail() {
    echo "$1" >&2
    echo 0 > /logs/verifier/reward.txt
    rc=1
    exit 1
}

if [ "$PWD" = "/" ]; then
    fail "Error: no working directory configured."
fi

CARGO_BIN="$(command -v cargo || true)"
if [ -z "$CARGO_BIN" ] && [ -x /usr/local/bin/cargo ]; then
    CARGO_BIN=/usr/local/bin/cargo
fi
if [ -z "$CARGO_BIN" ] && [ -x /usr/local/cargo/bin/cargo ]; then
    CARGO_BIN=/usr/local/cargo/bin/cargo
fi
if [ -z "$CARGO_BIN" ] || [ ! -x "$CARGO_BIN" ]; then
    fail "Cargo is unavailable."
fi

BUILD_LOG_DIR=/tmp/cmake-reconciler-build
mkdir -p "$BUILD_LOG_DIR"
BUILD_LOG="$BUILD_LOG_DIR/candidate_build.log"

rm -rf /app/target
rm -f /app/output/resolution_report.json /app/output/resolution_report.json.tmp

if ! (
    cd /app
    "$CARGO_BIN" build --release --locked --offline
) > "$BUILD_LOG" 2>&1; then
    echo "Candidate release build failed." >&2
    cat "$BUILD_LOG" >&2
    fail "Candidate release build failed."
fi

CANDIDATE_BIN=/app/target/release/cmake-reconciler
if [ ! -x "$CANDIDATE_BIN" ]; then
    fail "Expected native release binary is missing: $CANDIDATE_BIN"
fi

export CANDIDATE_BIN
export ISOLATION_WRAPPER="${ISOLATION_WRAPPER:-/tests/run_candidate_isolated.sh}"
export CMAKE_DATA_DIR="${CMAKE_DATA_DIR:-/app/data}"

COLLECT_OUTPUT="$(
    python3 -I -m pytest \
        --confcutdir=/tests \
        -o cache_dir=/tmp/pytest_cache \
        --collect-only -q \
        /tests/test_outputs.py 2>&1
)"
COLLECT_RC=$?
printf '%s\n' "$COLLECT_OUTPUT"
if [ "$COLLECT_RC" -ne 0 ]; then
    fail "pytest collection failed."
fi
if ! printf '%s\n' "$COLLECT_OUTPUT" | grep -Eq '23 tests collected|23 collected'; then
    fail "Expected exactly 23 candidate-facing tests."
fi

rm -f "$BUILD_LOG"

python3 -I -m pytest \
    --confcutdir=/tests \
    -o cache_dir=/tmp/pytest_cache \
    --ctrf /logs/verifier/ctrf.json \
    /tests/test_outputs.py \
    -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
