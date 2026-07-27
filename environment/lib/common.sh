#!/usr/bin/env bash
# shared helpers

ROOT="${ROOT:-/app/environment}"

die() {
  echo "err: $*" >&2
  exit 1
}

ensure_dir() {
  local d
  for d in "$@"; do
    mkdir -p "$d"
  done
}

read_kv_toml_boost() {
  # args: toml_path filename -> prints integer boost (default 0)
  local toml="$1"
  local fname="$2"
  local line
  line=$(grep -E "^\"${fname}\"[[:space:]]*=" "$toml" 2>/dev/null | head -n1 || true)
  if [[ -z "$line" ]]; then
    echo 0
    return 0
  fi
  echo "$line" | sed -E 's/.*=[[:space:]]*([-0-9]+).*/\1/'
}

path_key_from_fc() {
  # strip (/.*)? suffix for matching short paths
  local p="$1"
  echo "${p%%\(/.*)?*}"
}
