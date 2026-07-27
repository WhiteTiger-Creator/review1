args <- commandArgs(trailingOnly = TRUE)
input_dir <- if (length(args) >= 1) args[[1]] else "/app/data"
output_dir <- if (length(args) >= 2) args[[2]] else "/app/outputs"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
training <- read.csv(file.path(input_dir, "training_digits.csv"), stringsAsFactors = FALSE, check.names = FALSE)
evaluation <- read.csv(file.path(input_dir, "evaluation_digits.csv"), stringsAsFactors = FALSE, check.names = FALSE)
columns <- as.vector(rbind(paste0("x", 1:8), paste0("y", 1:8)))
train <- as.matrix(training[, columns]) / 100
eval <- as.matrix(evaluation[, columns]) / 100
weights <- as.numeric(training$policy_weight)
center <- colSums(train * weights) / sum(weights)
spread <- sqrt(colSums(((train - rep(center, each = nrow(train))) ^ 2) * weights) / sum(weights))
spread[spread < 1e-6] <- 1
train <- sweep(sweep(train, 2, center, "-"), 2, spread, "/")
eval <- sweep(sweep(eval, 2, center, "-"), 2, spread, "/")
scores <- matrix(0, nrow = nrow(eval), ncol = 10)
for (digit in 0:9) {
  mask <- training$digit_label == digit
  class_weights <- weights[mask]
  class_matrix <- train[mask, , drop = FALSE]
  mean_vec <- colSums(class_matrix * class_weights) / sum(class_weights)
  variance <- colSums(((class_matrix - rep(mean_vec, each = nrow(class_matrix))) ^ 2) * class_weights) / sum(class_weights) + 0.2
  diff <- eval - rep(mean_vec, each = nrow(eval))
  scores[, digit + 1] <- -0.5 * rowSums((diff ^ 2) / rep(variance, each = nrow(eval)))
}
scores <- scores / 4
scores <- scores - apply(scores, 1, max)
probabilities <- exp(scores)
probabilities <- probabilities / rowSums(probabilities)
probabilities <- 0.97 * probabilities + 0.03 / 10
probabilities <- probabilities / rowSums(probabilities)
output <- data.frame(record_id = evaluation$record_id, probabilities)
names(output) <- c("record_id", paste0("p_", 0:9))
write.csv(output, file.path(output_dir, "digit_probabilities.csv"), row.names = FALSE, quote = FALSE)
