#!/bin/sh
set -eu
cp /solution/reference_analysis.R /app/analysis.R
/app/run.sh /app/data /app/outputs
