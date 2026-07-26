#!/bin/sh
set -eu
input_dir="${1:-/app/data}"
output_dir="${2:-/app/outputs}"
mkdir -p "$output_dir"
Rscript /app/analysis.R "$input_dir" "$output_dir"
