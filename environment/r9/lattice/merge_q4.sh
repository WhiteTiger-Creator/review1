#!/usr/bin/env bash
# Decoy — dry-run preview of drop-in fragments

merge_q4() {
  local dropin_dir="$1"
  local out_txt="$2"
  {
    echo "preview"
    local f
    for f in "$dropin_dir"/*.fc; do
      [[ -f "$f" ]] || continue
      echo "== $(basename "$f") =="
      cat "$f"
    done
  } >"$out_txt"
}
