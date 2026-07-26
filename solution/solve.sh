#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE=""
for candidate in \
    "$SCRIPT_DIR/reference/ReferenceAudit.java" \
    /solution/reference/ReferenceAudit.java \
    /oracle/reference/ReferenceAudit.java; do
    if [ -f "$candidate" ]; then
        SOURCE="$candidate"
        break
    fi
done

if [ -z "$SOURCE" ]; then
    echo "reference source not found" >&2
    exit 1
fi

mkdir -p /app/src/audit
sed \
    -e 's/^package refaudit;$/package audit;/' \
    -e 's/public final class ReferenceAudit/public final class Main/' \
    "$SOURCE" > /app/src/audit/Main.java

chmod 0755 /app/bin/weka-cv-audit
/app/bin/weka-cv-audit \
    --data /app/examples/sites.arff \
    --class species \
    --id sample_id \
    --group site \
    --top 2 \
    --out /app/report.json
