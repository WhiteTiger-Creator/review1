args <- commandArgs(trailingOnly = TRUE)
input_dir <- if (length(args) >= 1) args[[1]] else "/app/data"
output_dir <- if (length(args) >= 2) args[[2]] else "/app/outputs"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
training <- read.csv(file.path(input_dir, "training_digits.csv"), stringsAsFactors = FALSE, check.names = FALSE)
evaluation <- read.csv(file.path(input_dir, "evaluation_digits.csv"), stringsAsFactors = FALSE, check.names = FALSE)
weights <- as.numeric(training$policy_weight)
counts <- tapply(weights, training$digit_label, sum)
probabilities <- as.numeric(counts[as.character(0:9)] + 1)
probabilities <- probabilities / sum(probabilities)
output <- data.frame(record_id = evaluation$record_id, matrix(rep(probabilities, each = nrow(evaluation)), ncol = 10))
names(output) <- c("record_id", paste0("p_", 0:9))
write.csv(output, file.path(output_dir, "digit_probabilities.csv"), row.names = FALSE, quote = FALSE)
