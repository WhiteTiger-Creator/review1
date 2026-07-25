args <- commandArgs(trailingOnly = TRUE)
output_file <- if (length(args) >= 2L) {
  args[[2]]
} else {
  "/app/outputs/results.csv"
}

columns <- c(
  "case_id",
  "selected_lambda",
  "selected_policy",
  "feasible_count",
  "policy_score",
  "robust_policy_return",
  "minimum_cycle_mean",
  "critical_cycle",
  "effective_sample_size",
  "cv_loss",
  "deletion_code",
  "deletion_change_count",
  "worst_deletion_safety",
  "worst_deletion_scenario_code",
  "stability_checksum",
  "audit_signature"
)
dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
writeLines(paste(columns, collapse = ","), output_file)
