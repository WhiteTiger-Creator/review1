args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args) >= 1) args[1] else "/app/data"
output <- if (length(args) >= 2) args[2] else "/app/outputs"

training_events <- read.csv(file.path(input, "training_choices.csv"), stringsAsFactors = FALSE)
training_candidates <- read.csv(file.path(input, "training_candidates.csv"), stringsAsFactors = FALSE)
evaluation_events <- read.csv(file.path(input, "evaluation_choices.csv"), stringsAsFactors = FALSE)
evaluation_candidates <- read.csv(file.path(input, "evaluation_candidates.csv"), stringsAsFactors = FALSE)

training_events <- training_events[order(training_events$event_id), ]
training_candidates <- training_candidates[order(training_candidates$event_id, training_candidates$item_id), ]
evaluation_events <- evaluation_events[order(evaluation_events$event_id), ]
evaluation_candidates <- evaluation_candidates[order(evaluation_candidates$event_id, evaluation_candidates$item_id), ]

training <- merge(training_candidates, training_events, by = "event_id", sort = TRUE)
evaluation <- merge(evaluation_candidates, evaluation_events, by = "event_id", sort = TRUE)
training$is_clicked <- as.integer(training$item_id == training$clicked_item)
training$event_weight <- pmin(10, 1 / training$behavior_propensity)
training$source <- "training"
evaluation$is_clicked <- 0L
evaluation$event_weight <- 1
evaluation$source <- "evaluation"

fields <- c(
  "event_id", "item_id", "item_feature_0", "item_feature_1", "item_feature_2",
  "item_feature_3", "affinity", "campaign", "position", "user_feature_0",
  "is_clicked", "event_weight", "source"
)
combined <- rbind(training[fields], evaluation[fields])
combined$campaign <- factor(combined$campaign)
combined$position <- factor(combined$position)
combined$user_feature_0 <- factor(combined$user_feature_0)
combined$item_feature_1 <- factor(combined$item_feature_1)
combined$item_feature_2 <- factor(combined$item_feature_2)
combined$item_feature_3 <- factor(combined$item_feature_3)

design <- model.matrix(
  ~ 0 + item_feature_1 + item_feature_2 + item_feature_3 + affinity +
    item_feature_0:campaign + item_feature_0:position +
    item_feature_0:user_feature_0,
  data = combined
)
train_index <- which(combined$source == "training")
evaluation_index <- which(combined$source == "evaluation")
x_train <- design[train_index, , drop = FALSE]
x_evaluation <- design[evaluation_index, , drop = FALSE]
train_rows <- combined[train_index, ]
evaluation_rows <- combined[evaluation_index, ]
groups <- split(seq_len(nrow(train_rows)), train_rows$event_id)
clicked <- vapply(
  groups,
  function(index) index[which(train_rows$is_clicked[index] == 1)],
  integer(1)
)
weights <- vapply(
  groups,
  function(index) train_rows$event_weight[index[1]],
  numeric(1)
)
ridge <- 8

objective <- function(beta) {
  eta <- as.vector(x_train %*% beta)
  loss <- 0.5 * ridge * sum(beta * beta)
  gradient <- ridge * beta
  group_number <- 0L
  for (index in groups) {
    group_number <- group_number + 1L
    local_eta <- eta[index]
    local_eta <- local_eta - max(local_eta)
    probability <- exp(local_eta)
    probability <- probability / sum(probability)
    chosen <- clicked[group_number]
    weight <- weights[group_number]
    chosen_local <- which(index == chosen)
    loss <- loss - weight * log(max(probability[chosen_local], 1e-15))
    gradient <- gradient + weight * (
      colSums(x_train[index, , drop = FALSE] * probability) - x_train[chosen, ]
    )
  }
  list(value = loss, gradient = gradient)
}

fit <- optim(
  rep(0, ncol(x_train)),
  fn = function(beta) objective(beta)$value,
  gr = function(beta) objective(beta)$gradient,
  method = "L-BFGS-B",
  control = list(maxit = 250, factr = 1e7)
)

evaluation_rows$score <- as.vector(x_evaluation %*% fit$par)
evaluation_groups <- split(seq_len(nrow(evaluation_rows)), evaluation_rows$event_id)
evaluation_rows$probability <- 0
for (index in evaluation_groups) {
  eta <- evaluation_rows$score[index]
  eta <- eta - max(eta)
  probability <- exp(eta)
  evaluation_rows$probability[index] <- probability / sum(probability)
}

result <- evaluation_rows[c("event_id", "item_id", "probability")]
result <- result[order(result$event_id, result$item_id), ]
dir.create(output, recursive = TRUE, showWarnings = FALSE)
write.csv(
  result,
  file.path(output, "choice_predictions.csv"),
  row.names = FALSE,
  quote = FALSE
)
