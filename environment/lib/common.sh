#!/usr/bin/env bash

readonly LEDGER_PATH="/app/ground-canon/ground-lockdown-ledger-v1.json"
readonly CATALOG_PATH="/app/config/sysctl-module-catalog.json"

fail() {
  local code="$1"
  shift
  printf '%s\n' "$*" >&2
  exit "$code"
}

require_absolute() {
  [[ "$1" == /* ]] || fail 64 "paths must be absolute"
}

require_input() {
  require_absolute "$1"
  [[ -r "$1" && -f "$1" ]] || fail 66 "input is not readable: $1"
}

atomic_write_bytes() {
  local destination="$1"
  local payload="$2"
  local parent temporary
  parent=$(dirname "$destination")
  [[ -d "$parent" ]] || fail 73 "output directory does not exist: $parent"
  temporary=$(mktemp "$parent/.fortify.XXXXXX") || fail 73 "cannot create output"
  if ! printf '%s' "$payload" > "$temporary"; then
    rm -f "$temporary"
    fail 73 "cannot write output"
  fi
  mv -f "$temporary" "$destination" || {
    rm -f "$temporary"
    fail 73 "cannot replace output"
  }
}
