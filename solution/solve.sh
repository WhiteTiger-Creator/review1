#!/bin/bash
set -euo pipefail

solution_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

install -m 0644 "$solution_dir/reference/desk_derive.jl" /app/desk_derive.jl
install -m 0644 "$solution_dir/reference/csv_load.jl" /app/src/csv_load.jl
install -m 0644 "$solution_dir/reference/policy_load.jl" /app/src/policy_load.jl
install -m 0644 "$solution_dir/reference/compensate.jl" /app/src/compensate.jl
install -m 0644 "$solution_dir/reference/weights.jl" /app/src/weights.jl
install -m 0644 "$solution_dir/reference/report_emit.jl" /app/src/report_emit.jl
install -m 0644 "$solution_dir/reference/pabcal.jl" /app/pabcal.jl

/opt/julia/bin/julia --startup-file=no -e '
include("/app/desk_derive.jl")
write_derived_policy("/app/data/desk_journal.csv", "/app/config/cal_policy.toml")
'

want="$(tr -d '\r\n' < /app/data/sealed/production_policy.sha256)"
got="$(sha256sum /app/config/cal_policy.toml | awk '{print $1}')"
test "$want" = "$got"

bash /app/build.sh

set +e
/app/bin/pabcal --weights /tmp/oracle-weights_table.csv --report /tmp/oracle-desk_summary.json
rc=$?
set -e
if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
  exit "$rc"
fi

test -f /tmp/oracle-weights_table.csv
test -f /tmp/oracle-desk_summary.json
