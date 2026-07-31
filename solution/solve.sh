#!/bin/bash
set -euo pipefail

cp /solution/answer_correct.cypher /app/answer.cypher

output=$(python3 /app/bin/run_query.py "$(cat /app/answer.cypher)")
row_count=$(echo "$output" | tail -n +2 | wc -l)
if [ "$row_count" -lt 1 ]; then
  echo "solve.sh: expected at least one result row, got $row_count" 1>&2
  exit 1
fi
