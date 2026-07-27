#!/usr/bin/env bash
# IO helpers for harbor

harbor_write_line() {
  local path="$1"
  local line="$2"
  printf '%s\n' "$line" >"$path"
}

harbor_read_line() {
  local path="$1"
  head -n1 "$path"
}
