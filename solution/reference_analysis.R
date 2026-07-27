args <- commandArgs(trailingOnly = TRUE)
input_dir <- if (length(args) >= 1) args[[1]] else "/app/data"
output_dir <- if (length(args) >= 2) args[[2]] else "/app/outputs"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

read_table <- function(name) {
  read.csv(file.path(input_dir, name), stringsAsFactors = FALSE, check.names = FALSE)
}

coordinate_matrix <- function(frame) {
  columns <- as.vector(rbind(paste0("x", 1:8), paste0("y", 1:8)))
  as.matrix(frame[, columns])
}

features_from_coordinates <- function(raw) {
  x <- raw[, seq(1, 15, 2), drop = FALSE] / 100
  y <- raw[, seq(2, 16, 2), drop = FALSE] / 100
  dx <- x[, 2:8, drop = FALSE] - x[, 1:7, drop = FALSE]
  dy <- y[, 2:8, drop = FALSE] - y[, 1:7, drop = FALSE]
  lengths <- sqrt(dx * dx + dy * dy)
  angles <- atan2(dy, dx)
  turns <- angles[, 2:7, drop = FALSE] - angles[, 1:6, drop = FALSE]
  turns <- (turns + pi) %% (2 * pi) - pi
  cbind(
    raw / 100,
    dx,
    dy,
    lengths,
    abs(dx),
    abs(dy),
    turns,
    rowMeans(x),
    rowMeans(y),
    apply(x, 1, sd),
    apply(y, 1, sd),
    apply(x, 1, max) - apply(x, 1, min),
    apply(y, 1, max) - apply(y, 1, min),
    x[, 1],
    y[, 1],
    x[, 8],
    y[, 8],
    x[, 8] - x[, 1],
    y[, 8] - y[, 1],
    rowSums(lengths)
  )
}

weighted_probabilities <- function(train_features, train_labels, eval_features, weights) {
  weights <- as.numeric(weights)
  center <- colSums(train_features * weights) / sum(weights)
  spread <- sqrt(colSums(((train_features - rep(center, each = nrow(train_features))) ^ 2) * weights) / sum(weights))
  spread[!is.finite(spread) | spread < 1e-6] <- 1
  train_scaled <- sweep(sweep(train_features, 2, center, "-"), 2, spread, "/")
  eval_scaled <- sweep(sweep(eval_features, 2, center, "-"), 2, spread, "/")
  k <- 7
  blend <- 0.01
  train_norm <- rowSums(train_scaled * train_scaled)
  probabilities <- matrix(0, nrow = nrow(eval_scaled), ncol = 10)
  for (start in seq(1, nrow(eval_scaled), by = 150)) {
    stop <- min(nrow(eval_scaled), start + 149)
    block <- eval_scaled[start:stop, , drop = FALSE]
    distances <- outer(rowSums(block * block), train_norm, "+") - 2 * tcrossprod(block, train_scaled)
    distances[distances < 0] <- 0
    for (offset in seq_len(nrow(block))) {
      neighbors <- order(distances[offset, ])[seq_len(k)]
      local_weight <- weights[neighbors] / (distances[offset, neighbors] + 1e-5)
      totals <- rep(blend / 10, 10)
      for (neighbor in seq_along(neighbors)) {
        label <- train_labels[neighbors[neighbor]] + 1
        totals[label] <- totals[label] + (1 - blend) * local_weight[neighbor]
      }
      probabilities[start + offset - 1, ] <- totals / sum(totals)
    }
  }
  probabilities
}

training <- read_table("training_digits.csv")
evaluation <- read_table("evaluation_digits.csv")
train_features <- features_from_coordinates(coordinate_matrix(training))
eval_features <- features_from_coordinates(coordinate_matrix(evaluation))
probabilities <- weighted_probabilities(
  train_features,
  as.integer(training$digit_label),
  eval_features,
  as.numeric(training$policy_weight)
)
output <- data.frame(record_id = evaluation$record_id, probabilities, check.names = FALSE)
names(output) <- c("record_id", paste0("p_", 0:9))
write.csv(output, file.path(output_dir, "digit_probabilities.csv"), row.names = FALSE, quote = FALSE)
