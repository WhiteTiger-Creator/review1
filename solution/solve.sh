#!/bin/bash
set -euo pipefail

cd /app
find /app -maxdepth 3 -type f -print | sort
sed -n '1,240p' /app/contracts/output_contract.md
head -n 2 /app/data/train.csv
head -n 2 /app/data/score.csv

{
    sed -n '1p' /solution/analysis.R
    printf '%s\n' '# Oracle solution: derives all artifacts from the public inputs.'
    sed -n '2,$p' /solution/analysis.R
} > /app/analysis.R
chmod 0755 /app/analysis.R
Rscript /app/analysis.R
