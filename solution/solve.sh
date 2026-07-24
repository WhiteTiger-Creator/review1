#!/bin/bash
set -euo pipefail

mkdir -p /app/task_file/output /tmp/abi-transition-solver
g++ -std=c++20 -O2 /solution/solver.cpp -o /tmp/abi-transition-solver/solver

for mapping in \
    "abi_case.txt:abi_plan.json" \
    "branching_case.txt:branching_plan.json" \
    "cohort_case.txt:cohort_plan.json" \
    "tie_case.txt:tie_plan.json"; do
    input_name="${mapping%%:*}"
    output_name="${mapping#*:}"
    /tmp/abi-transition-solver/solver \
        "/app/task_file/scan_input/${input_name}" \
        "/app/task_file/output/${output_name}"
done
