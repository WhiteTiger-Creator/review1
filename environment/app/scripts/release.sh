#!/bin/bash
# Broken packaging stub — missing share layout, smoke, archives, and reports.
set -euo pipefail
ROOT=/app
DIST=$ROOT/dist
rm -rf "$DIST"
mkdir -p "$DIST/bundles"
echo '{"format_version":1}' > "$DIST/nuget-report.json"
echo "release stub incomplete — see /app/docs/nuget-contract.md and release-contract.md" >&2
exit 1
