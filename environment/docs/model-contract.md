# Model contract: crater vs clean e-coat classifier

This file is the binding schema for /app/analysis.R. It fixes the model family, the artifact
files, and the numeric conventions the verifier recomputes. Every value here matches
/app/config/model_config.csv, /app/config/feature_roles.csv, /app/config/costs.csv, and
/app/config/report_contract.csv. Where a per-artifact note in /app/config/report_contract.csv
governs ordering, selection, or binning, that note is authoritative and is not restated in full
here.

## Runtime and paths

- Entry point: `Rscript /app/analysis.R`. The runtime is base R plus jsonlite, offline, and
  deterministic: identical inputs produce identical artifacts on every rerun.
- The verifier may relocate the inputs and outputs through these environment variables.
  /app/analysis.R must read them and fall back to the defaults shown when they are unset:
  - `CONFIG_DIR` (default /app/config): holds model_config.csv, feature_roles.csv, costs.csv,
    and report_contract.csv.
  - `DATA_DIR` (default /app/data) and `DATA_PATH` (default <DATA_DIR>/train.csv): the single
    input table.
  - `OUT_DIR`, falling back to `OUTPUT_DIR` (default /app/outputs): the directory every artifact
    below is written into.
- All artifact tables are written into the /app/outputs/ directory (the default OUT_DIR). Never
  /app/reports/ or any other name.

## Data and splits

- /app/data/train.csv holds one coated panel per row. Key columns: id panel_id, target cratered,
  group bath_run, split split_role.
- split_role takes the values fit, validation, and test. cratered is filled for fit and
  validation rows and blank for test rows.
- Feature columns, in /app/config/feature_roles.csv order: numeric film_microns, bath_solids,
  bath_temp_c, coat_voltage, dip_seconds, rinse_pressure; categorical substrate_grade, line_side,
  pretreat_type. bath_solids, coat_voltage, and pretreat_type carry blanks that must be imputed.
- The class order is clean then cratered; the positive class is cratered.

## Model family (checkable constraints)

- A k-nearest-neighbour classifier trained on tabular rows. All imputation and scaling statistics
  are estimated from fit rows only and applied unchanged to the validation and test rows.
- k is chosen from the grid 3, 5, 7, 11, 15 in /app/config/model_config.csv by validation
  macro-F1.
- The winning k is refit on the fit and validation rows together before the test rows are scored.
- The operating threshold is chosen from the grid 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55,
  0.60, 0.65, 0.70 using the cost table in /app/config/costs.csv (false_positive_cost 1.0,
  false_negative_cost 4.0).
- Reruns are deterministic.

## Artifacts (all written into /app/outputs/)

Columns are listed in required order. panel ids, k values, counts, and n_* row counts are integers;
probabilities, distances, costs, and metrics are decimals. The flag columns selected, correct, and
loo_correct MUST be the integer digits 1 or 0, never TRUE/FALSE.

- predictions.csv: panel_id, pred_label, bath_run, prob_clean, prob_cratered. One row per
  test (held-out) record, ascending panel_id; pred_label uses the operating threshold.
- validation_predictions.csv: panel_id, actual, pred_label, correct, bath_run, prob_clean,
  prob_cratered. One row per validation record, ascending panel_id; correct is 1 when pred_label
  equals actual, else 0.
- metrics.json: a single JSON object with task_kind, target_column, selected_k,
  operating_threshold, n_fit, n_validation, n_test, validation_accuracy, validation_macro_f1,
  validation_expected_cost. task_kind is "binary" and target_column is "cratered". selected_k is
  one grid k and operating_threshold one grid threshold. All numeric fields are rounded to 6
  decimals.
- selection_report.csv: candidate_k, validation_macro_f1, selected. One row per k in grid order;
  exactly one row has selected = 1, and its candidate_k equals metrics.json selected_k.
- threshold_report.csv: threshold, false_positives, false_negatives, expected_cost,
  worst_group_cost, selected. One row per configured threshold in grid order; the selected row
  (selected = 1) minimizes worst_group_cost, ties to the earlier grid entry.
- confusion_matrix.csv: actual, predicted, count. Validation rows; outer loop actual, inner loop
  predicted, both in class order.
- class_metrics.csv: class, precision, recall, f1, support. Validation rows; classes in class
  order.
- calibration_bins.csv: bin_low, bin_high, count, mean_predicted, observed_rate. Five fixed-width
  bins over the positive-class probability; empty bins report zeros.
- group_error_report.csv: group_value, n_validation, accuracy. Validation rows grouped by bath_run,
  ascending group_value.
- feature_summary.csv: feature, data_type, missing_fit, missing_validation, missing_test. The
  configured features in feature_roles order, with the missing count per split.
- neighbor_evidence.csv: panel_id, nearest_reference_id, nearest_distance. The first 50 held-out
  rows by panel_id; the nearest refit-reference record and its distance.
- fit_reference_calibration.csv: bin, lower_edge, upper_edge, count, mean_predicted, observed_rate.
  Five bins whose interior edges are the fit-set leave-one-out probability order statistics;
  validation rows are binned by those edges as /app/config/report_contract.csv specifies.
- neighbor_detail.csv: panel_id, neighbor_rank, neighbor_id, distance, weight_share. The first 40
  held-out rows by panel_id; the selected-k refit neighbors ordered as
  /app/config/report_contract.csv states. The weight_share values within a row sum to 1.
- loo_audit.csv: panel_id, actual, loo_positive_prob, loo_pred_label, loo_correct. See the
  leave-one-out rule below.

## Pinned semantics (part of the schema)

- expected_cost in threshold_report.csv is the cost-weighted error total divided by the number of
  validation rows: (false_positive_cost * false_positives + false_negative_cost *
  false_negatives) / n_validation. validation_expected_cost in metrics.json uses the same formula
  over all validation rows. worst_group_cost applies the same cost-weighted error divided by the
  group size within each bath_run group and takes the maximum across groups.
- loo_audit.csv covers exactly the fit rows at the 1-based positions 1 + stride * (0..11) of the
  id-sorted fit set, where stride = max(1, floor(n_fit / 12)); that yields 12 rows.
  loo_positive_prob is the leave-one-out positive-class probability at the selected k,
  loo_pred_label applies the operating threshold, and loo_correct is 1 when loo_pred_label equals
  actual, else 0.

## Grading

Every report must be an honest account of the model that /app/analysis.R actually fits. The
verifier reruns /app/analysis.R, recomputes each table from the serialized probabilities, and
checks the reports for internal self-consistency against those probabilities. The accuracy and
macro-F1 quality floors are judged on withheld true test labels, not on any number the reports
declare, and there is no iterative feedback. Careless imputation or scaling misses the floors.
