#!/usr/bin/env bash
set -euo pipefail

# Copy the independent native Rust Oracle over /app and rebuild offline.

APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORACLE_SRC="${SCRIPT_DIR}/oracle_src"

CARGO_HOME="${CARGO_HOME:-/usr/local/cargo}"
RUSTUP_HOME="${RUSTUP_HOME:-/usr/local/rustup}"
export CARGO_HOME RUSTUP_HOME
export PATH="${CARGO_HOME}/bin:${RUSTUP_HOME}/bin:/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ ! -d "${ORACLE_SRC}/src" ]]; then
  echo "oracle_src missing at ${ORACLE_SRC}" >&2
  exit 1
fi

rm -rf "${APP_ROOT}/src"
mkdir -p "${APP_ROOT}/src"
# Copy library/bin sources without author-only self_check binary.
shopt -s nullglob
for f in "${ORACLE_SRC}/src"/*.rs; do
  cp -a "$f" "${APP_ROOT}/src/"
done
shopt -u nullglob

cp -f "${ORACLE_SRC}/Cargo.toml" "${APP_ROOT}/Cargo.toml"
python3 - "${APP_ROOT}/Cargo.toml" <<'PY'
from pathlib import Path
import re
import sys
p = Path(sys.argv[1])
text = p.read_text()
text = re.sub(
    r'\n\[\[bin\]\]\nname = "oracle-self-check"\npath = "src/bin/self_check.rs"\n',
    "\n",
    text,
)
p.write_text(text)
PY
if [[ -f "${ORACLE_SRC}/Cargo.lock" ]]; then
  cp -f "${ORACLE_SRC}/Cargo.lock" "${APP_ROOT}/Cargo.lock"
fi

find "${APP_ROOT}/src" -type f -name '*.rs' -exec touch {} +
rm -f "${APP_ROOT}/target/release/webauthn-assertion-worker" \
      "${APP_ROOT}/target/release/webauthn-assertion-worker.d" 2>/dev/null || true
find "${APP_ROOT}/target/release/.fingerprint" "${APP_ROOT}/target/release/deps" \
  -maxdepth 1 \( \
    -name 'webauthn-assertion-worker-*' \
    -o -name 'webauthn_assertion_worker-*' \
    -o -name 'libwebauthn_assertion_worker-*' \
  \) -exec rm -rf {} + 2>/dev/null || true

cd "${APP_ROOT}"
cargo build --release --locked --offline

BIN="${APP_ROOT}/target/release/webauthn-assertion-worker"
if [[ ! -x "${BIN}" ]]; then
  mapfile -t bins < <(find "${APP_ROOT}/target/release" -maxdepth 1 -type f -executable ! -name '*.d' ! -name '.*')
  if [[ ${#bins[@]} -ne 1 ]]; then
    echo "expected exactly one release binary, found: ${bins[*]:-none}" >&2
    exit 1
  fi
  BIN="${bins[0]}"
fi

mkdir -p "${APP_ROOT}/output"
DB_BACKUP="$(mktemp)"
cp "${APP_ROOT}/data/audit.sqlite" "${DB_BACKUP}"
"${BIN}" \
  --database "${APP_ROOT}/data/audit.sqlite" \
  --as-of "2026-07-01T12:00:00Z" \
  --output "${APP_ROOT}/output/report.json"

cp "${DB_BACKUP}" "${APP_ROOT}/data/audit.sqlite"
rm -f "${DB_BACKUP}"

echo "Oracle wrote ${APP_ROOT}/output/report.json"
