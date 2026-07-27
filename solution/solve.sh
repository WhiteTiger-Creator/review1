#!/usr/bin/env bash
set -euo pipefail

solution_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
analysis_r="$solution_dir/reference_analysis.R"
if [ ! -f "$analysis_r" ]; then
    for candidate_dir in /oracle /solution; do
        if [ -f "$candidate_dir/reference_analysis.R" ]; then
            analysis_r="$candidate_dir/reference_analysis.R"
            break
        fi
    done
fi

if [ ! -f "$analysis_r" ]; then
    echo "solve.sh: cannot locate reference_analysis.R" >&2
    exit 1
fi

cp "$analysis_r" /app/analysis.R
/app/run.sh /app/data /app/outputs
