#!/usr/bin/env bash
set -euo pipefail

exec Rscript /app/estimate.R "${1:-/app/data}" "${2:-/app/outputs/results.csv}"
