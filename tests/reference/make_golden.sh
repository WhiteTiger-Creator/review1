#!/bin/bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
task="$(cd "$here/../.." && pwd)"
ref="$(mktemp -d)/wheel"
bash "$here/build_reference.sh" "$ref" >/dev/null
rm -rf "$task/tests/golden"
mkdir -p "$task/tests/golden"
for input in "$task/environment/inputs"/*.bin "$task/tests/inputs_hidden"/*.bin; do
  name="$(basename "$input")"
  set +e
  "$ref" < "$input" > "$task/tests/golden/$name.out"
  code=$?
  set -e
  printf '%d' "$code" > "$task/tests/golden/$name.code"
done
ls "$task/tests/golden" | wc -l
