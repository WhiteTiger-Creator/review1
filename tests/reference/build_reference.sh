#!/bin/bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/wheel}"
SOURCE_DATE_EPOCH=1700000000 gcc -std=c11 -O2 -Wall -Wextra \
  -fno-asynchronous-unwind-tables -ffile-prefix-map="$here"=. \
  -frandom-seed=twcs -o "$out" "$here/original.c"
strip -s "$out"
sha256sum "$out"
