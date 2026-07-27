#!/usr/bin/env bash
# Drop-in scanner utility

scan_dir() {
  local dropin_dir="$1"
  local out_list="$2"
  ls -1 "$dropin_dir"/*.fc 2>/dev/null | sort >"$out_list"
}
