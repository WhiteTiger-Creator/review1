#!/bin/bash
# Verifier-owned mirror replay. Invokes only freshly built binaries as an
# unprivileged user against MIRROR_ROOT; never calls agent-editable helpers.
set -euo pipefail

root="${MIRROR_ROOT:-/app/environment}"
out="${OUTPUT_DIR:-/app/output}"
bin_root="${VERIFIER_BIN:-/tmp/verifier-bin}"
run_user="${VERIFIER_RUN_USER:-mirrun}"
cycles="${CYCLE_COUNT:-2}"

mirctl="${bin_root}/mirctl"
test -x "$mirctl"

rm -rf "$out"
mkdir -p "$out"

if [ -d "$root" ]; then
  parent="$root"
  while [ "$parent" != "/" ] && [ -n "$parent" ]; do
    chmod a+rx "$parent" 2>/dev/null || true
    parent="$(dirname "$parent")"
  done
  chmod -R a+rX "$root" 2>/dev/null || true
fi
chown -R "$run_user" "$out" "$root" 2>/dev/null || true

run_as() {
  runuser -u "$run_user" -- env "$@"
}

for ((i = 1; i <= cycles; i++)); do
  if [ "$i" -gt 1 ]; then
    run_as \
      MIRROR_ROOT="$root" \
      OUTPUT_DIR="$out" \
      CYCLE="$i" \
      APPEND_EXPORT=1 \
      "$mirctl" run "$out"
  else
    run_as \
      MIRROR_ROOT="$root" \
      OUTPUT_DIR="$out" \
      CYCLE="$i" \
      "$mirctl" run "$out"
  fi
done
