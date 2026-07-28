#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
SOLUTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -rf "${APP_ROOT}/auditor/target"
rm -rf "${APP_ROOT}/auditor/src"
mkdir -p "${APP_ROOT}/auditor/src"

cp -a "${SOLUTION_DIR}/oracle_src/src/." "${APP_ROOT}/auditor/src/"
cp -a "${SOLUTION_DIR}/oracle_src/Cargo.toml" "${APP_ROOT}/auditor/Cargo.toml"
if ! cmp -s "${SOLUTION_DIR}/oracle_src/Cargo.lock" "${APP_ROOT}/auditor/Cargo.lock"; then
  cp -a "${SOLUTION_DIR}/oracle_src/Cargo.lock" "${APP_ROOT}/auditor/Cargo.lock"
  rm -rf "${APP_ROOT}/auditor/vendor" "${APP_ROOT}/auditor/.cargo"
  cp -a "${SOLUTION_DIR}/oracle_src/vendor" "${APP_ROOT}/auditor/vendor"
  cp -a "${SOLUTION_DIR}/oracle_src/.cargo" "${APP_ROOT}/auditor/.cargo"
fi

cd "${APP_ROOT}/auditor"
cargo build --release --locked --offline

rm -f "${APP_ROOT}/output/audit_report.json"
mkdir -p "${APP_ROOT}/output"

"${APP_ROOT}/auditor/target/release/cargo-config-source-replacement-precedence-auditor" \
  --fixture-root "${APP_ROOT}/fixture-tree/config-root" \
  --requests "${APP_ROOT}/data/audit_requests.ndjson" \
  --environment-overrides "${APP_ROOT}/data/environment_overrides.json" \
  --cli-overrides "${APP_ROOT}/data/cli_overrides.ndjson" \
  --source-profiles "${APP_ROOT}/data/source_profiles.json" \
  --solver-config "${APP_ROOT}/data/solver_config.json" \
  --output "${APP_ROOT}/output/audit_report.json"

test -s "${APP_ROOT}/output/audit_report.json"
