#!/usr/bin/env bash
set -euo pipefail

write_reward() {
  mkdir -p /logs/verifier
  echo "$1" > /logs/verifier/reward.txt
}

fail() {
  echo "$1" >&2
  write_reward 0
  exit 1
}

if [ "$PWD" = "/" ]; then
  echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script." >&2
  write_reward 0
  exit 1
fi

write_reward 0

export CARGO_NET_OFFLINE=true
export CARGO_TERM_COLOR=never

command -v cargo >/dev/null || fail "cargo missing"
command -v rustc >/dev/null || fail "rustc missing"
command -v python3 >/dev/null || fail "python3 missing"

APP_ROOT="${APP_ROOT:-/app}"
TEST_DIR="${TEST_DIR:-/tests}"
export APP_ROOT TEST_DIR

rm -rf "${APP_ROOT}/auditor/target"
rm -f "${APP_ROOT}/output/audit_report.json" "${APP_ROOT}/output/audit_report.json.tmp"
mkdir -p "${APP_ROOT}/output"

# Protect private verifier assets from candidate tree
chmod -R a-w "${TEST_DIR}/reference" 2>/dev/null || true
chmod -R a-w "${TEST_DIR}/expected" 2>/dev/null || true

cd "${APP_ROOT}/auditor"
if ! cargo build --release --locked --offline; then
  fail "candidate auditor build failed"
fi

CANDIDATE_BIN="${APP_ROOT}/auditor/target/release/cargo-config-source-replacement-precedence-auditor"
if [ ! -x "${CANDIDATE_BIN}" ]; then
  fail "candidate binary missing"
fi
export CANDIDATE_BIN

# Author-side reference build validates oracle/reference agreement when present.
# Candidate-facing pytest grades public contracts + fixture-derived expectations.
# Intentionally do NOT export REFERENCE_BIN into candidate-facing pytest.
REF_DIR="${TEST_DIR}/reference"
REF_BUILD="${REF_DIR}"
if [ ! -w "${REF_DIR}" ]; then
  REF_BUILD="/tmp/auditor-reference-build"
  rm -rf "${REF_BUILD}"
  cp -a "${REF_DIR}" "${REF_BUILD}"
fi
cd "${REF_BUILD}"
if ! cargo build --release --locked --offline; then
  fail "reference build failed"
fi
REFERENCE_BIN="${REF_BUILD}/target/release/cargo-config-source-replacement-precedence-auditor"
if [ ! -x "${REFERENCE_BIN}" ]; then
  fail "reference binary missing"
fi

GOLDEN="${TEST_DIR}/expected/canonical_audit_report.json"
if [ ! -f "${GOLDEN}" ]; then
  fail "missing verifier-private golden report"
fi

# Validate reference output matches golden bytes (author/reference alignment gate).
REF_OUT="/tmp/reference-canonical-audit-report.json"
rm -f "${REF_OUT}" "${REF_OUT}.tmp"
"${REFERENCE_BIN}" \
  --fixture-root "${APP_ROOT}/fixture-tree/config-root" \
  --requests "${APP_ROOT}/data/audit_requests.ndjson" \
  --environment-overrides "${APP_ROOT}/data/environment_overrides.json" \
  --cli-overrides "${APP_ROOT}/data/cli_overrides.ndjson" \
  --source-profiles "${APP_ROOT}/data/source_profiles.json" \
  --solver-config "${APP_ROOT}/data/solver_config.json" \
  --output "${REF_OUT}" || fail "reference canonical run failed"
cmp -s "${REF_OUT}" "${GOLDEN}" || fail "reference output disagrees with golden report"

set +e
COLLECTED="$(python3 -m pytest --collect-only -q "${TEST_DIR}/test_outputs.py" 2>&1 | tail -n 1)"
collect_rc=$?
set -e
echo "pytest collection: ${COLLECTED}"
if [ "$collect_rc" -ne 0 ]; then
  fail "pytest collection failed"
fi
echo "${COLLECTED}" | grep -Eq '^26 tests collected' || fail "expected exactly 26 collected tests"

set +e
python3 -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json \
  "${TEST_DIR}/test_outputs.py" -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
