#!/bin/bash
# Authoring entry point. Rebuilds everything downstream of the reference source
# in one pass so the artifact, the traces, the goldens and the baselines can
# never drift apart. Not used at grading time.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
task="$(cd "$here/../.." && pwd)"
python="${PYTHON:-python3}"

# the reference source is owned by solution/ and only mirrored here
cp "$task/solution/solution.c" "$here/original.c"

"$python" "$here/gen_variants.py"
"$python" "$here/gen_fixtures.py"

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

"$python" "$here/gen_answer_map.py"

# the shipped artifact is the same source, stripped
bash "$here/build_reference.sh" "$task/environment/bin/timers"

ls "$task/tests/golden" | wc -l
