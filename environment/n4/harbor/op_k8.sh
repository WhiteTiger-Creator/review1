#!/usr/bin/env bash
# Decoy — human-readable book summary (ungraded)

op_k8() {
  local src_book="$1"
  local out_txt="$2"
  python3 - "$src_book" "$out_txt" <<'PY'
import json, sys
book = json.load(open(sys.argv[1]))
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    fh.write(f"tag={book.get('tag','')}\ncur={book.get('cur')}\nprev={book.get('prev')}\n")
PY
}
