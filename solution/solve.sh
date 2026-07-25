#!/bin/bash
set -euo pipefail
cp /solution/analysis_correct.R /app/analysis.R
cd /app
Rscript /app/analysis.R
if [ ! -f /app/estimate.json ]; then
  echo "oracle did not produce /app/estimate.json" >&2
  exit 1
fi
cat /app/estimate.json
