#!/bin/bash
set -euo pipefail

cp /solution/analysis.R /app/analysis.R
Rscript /app/analysis.R
test -s /app/outputs/predictions.csv
test -s /app/outputs/validation_predictions.csv
test -s /app/outputs/metrics.json
test -s /app/outputs/selection_report.csv
test -s /app/outputs/threshold_report.csv
test -s /app/outputs/confusion_matrix.csv
test -s /app/outputs/class_metrics.csv
test -s /app/outputs/calibration_bins.csv
test -s /app/outputs/group_error_report.csv
test -s /app/outputs/feature_summary.csv
test -s /app/outputs/neighbor_evidence.csv
test -s /app/outputs/fit_reference_calibration.csv
test -s /app/outputs/neighbor_detail.csv
test -s /app/outputs/loo_audit.csv
