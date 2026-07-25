#!/usr/bin/env bash
set -euo pipefail

cp /solution/estimate.R /app/estimate.R
/app/run.sh /app/data /app/outputs/results.csv
