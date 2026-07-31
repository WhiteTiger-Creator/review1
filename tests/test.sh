#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script." >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

APP_ROOT="${APP_ROOT:-/app}"
TEST_DIR="${TEST_DIR:-/tests}"
export APP_ROOT TEST_DIR

CARGO_HOME="${CARGO_HOME:-/usr/local/cargo}"
RUSTUP_HOME="${RUSTUP_HOME:-/usr/local/rustup}"
export CARGO_HOME RUSTUP_HOME
export PATH="${CARGO_HOME}/bin:${RUSTUP_HOME}/bin:/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -x /opt/venv/bin/python ]]; then
  PYTHON=/opt/venv/bin/python
else
  PYTHON=python3
fi

export PYTHONPATH="${TEST_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

if ! command -v cargo >/dev/null 2>&1; then
  echo "Cargo unavailable" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

rm -f "${APP_ROOT}/target/release/webauthn-assertion-worker" \
      "${APP_ROOT}/target/release/webauthn-assertion-worker.d" \
      "${APP_ROOT}/target/release/libwebauthn_assertion_worker.d" 2>/dev/null || true
find "${APP_ROOT}/target/release/.fingerprint" "${APP_ROOT}/target/release/deps" \
  -maxdepth 1 \( \
    -name 'webauthn-assertion-worker-*' \
    -o -name 'webauthn_assertion_worker-*' \
    -o -name 'libwebauthn_assertion_worker-*' \
  \) -exec rm -rf {} + 2>/dev/null || true

if ! cargo build --manifest-path "${APP_ROOT}/Cargo.toml" --release --locked --offline; then
  echo "Candidate build failed" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

BIN="${APP_ROOT}/target/release/webauthn-assertion-worker"
if [[ ! -x "${BIN}" ]]; then
  mapfile -t bins < <(find "${APP_ROOT}/target/release" -maxdepth 1 -type f -executable ! -name '*.d' ! -name '.*')
  if [[ ${#bins[@]} -eq 1 ]]; then
    BIN="${bins[0]}"
  else
    echo "Could not discover webauthn-assertion-worker release binary" >&2
    echo 0 > /logs/verifier/reward.txt
    exit 1
  fi
fi
export WEBAUTHN_WORKER_BINARY="${BIN}"

set +e
collect_out="$("${PYTHON}" -m pytest --collect-only -q "${TEST_DIR}/test_outputs.py" 2>&1)"
collect_rc=$?
set -e
echo "${collect_out}"
if [[ "${collect_rc}" -ne 0 ]]; then
  echo "pytest collection failed" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi
# Exact whole-token count: do not accept "124 tests" via substring "24 tests".
if ! echo "${collect_out}" | grep -Eq '(^|[^0-9])24 (tests?|items?)([^0-9]|$)'; then
  echo "Expected exactly 24 pytest tests, got: ${collect_out}" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi
if echo "${collect_out}" | grep -Eo '[0-9]+ (tests?|items?)' | awk '{print $1}' | grep -vq '^24$'; then
  echo "Expected exactly 24 pytest tests, got: ${collect_out}" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

set +e
"${PYTHON}" -m pytest \
  -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json \
  "${TEST_DIR}/test_outputs.py" \
  -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
