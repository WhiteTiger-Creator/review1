#!/bin/bash
set -euo pipefail

cd /app
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_file=""
for candidate in "$script_dir/scorer.js" /oracle/scorer.js /solution/scorer.js; do
    if [ -f "$candidate" ]; then
        source_file="$candidate"
        break
    fi
done

if [ -z "$source_file" ]; then
    echo "Missing scorer.js in solution mount" >&2
    exit 1
fi

install -m 0755 "$source_file" /app/bin/moonrail-route
node /app/bin/moonrail-route --input /app/task_file/samples/public_match.json --output /app/out/result.json
