#!/usr/bin/env bash
# Harbor bind helper

op_k7() {
  local src_book="$1"
  local compiled_snap="$2"
  local out_bind="$3"
  local prof="$4"
  local map_fp="$5"

  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/sha_util.sh"

  local cur tag merged_sha pre hex
  cur=$(python3 -c "import json;print(json.load(open('$src_book'))['cur'])")
  tag=$(python3 -c "import json;print(json.load(open('$src_book')).get('tag',''))")
  merged_sha=$(hex_sha256_file "$compiled_snap")

  pre="${cur}|${merged_sha}|${map_fp}|${prof}|${tag}"
  hex=$(hex_sha256_bytes "$pre")
  printf '%s\n' "$hex" >"$out_bind"
}
