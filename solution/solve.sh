#!/bin/bash
set -euo pipefail

cd /app/environment

python3 /solution/apply_fix.py

cp /solution/security_notes.md security_notes.md

go build ./...

echo "oracle: solve.sh complete"
