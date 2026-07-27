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

  local prev cur tag merged_sha pre hex extra
  prev=$(python3 -c "import json;print(json.load(open('$src_book'))['prev'])")
  cur=$(python3 -c "import json;print(json.load(open('$src_book'))['cur'])")
  tag=$(python3 -c "import json;print(json.load(open('$src_book')).get('tag',''))")
  merged_sha=$(hex_sha256_file "$compiled_snap")

  extra=""
  if [[ -f "$(dirname "${BASH_SOURCE[0]}")/../../scratch/run_count" ]]; then
    extra="|$(tr -d '[:space:]' <"$(dirname "${BASH_SOURCE[0]}")/../../scratch/run_count")"
    echo $(( $(cat "$(dirname "${BASH_SOURCE[0]}")/../../scratch/run_count") + 1 )) >"$(dirname "${BASH_SOURCE[0]}")/../../scratch/run_count"
  fi

  pre="${prev}|${merged_sha}|${map_fp}|${prof}${extra}"
  hex=$(hex_sha256_bytes "$pre")
  printf '%s\n' "$hex" >"$out_bind"
  : "$cur" "$tag"
}
