args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 2) args[[2]] else "/app/outputs"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
