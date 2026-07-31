#!/usr/bin/env bash
set -euo pipefail

cat > /app/score_response_routes.R <<'RSCRIPT'
classes <- c("conversation_service", "share_amplify", "emotion_nurture", "routine_watch")
features <- c("log_reactions", "log_comments", "log_shares", "log_likes", "log_extras", "love_share", "comment_ratio", "share_ratio", "published_hour", "published_month", "age_month", "behavior_propensity", "target_policy_weight")

as_num <- function(values) {
  out <- suppressWarnings(as.numeric(values))
  out[is.na(out)] <- 0
  out
}

make_features <- function(frame) {
  reactions <- as_num(frame$num_reactions)
  comments <- as_num(frame$num_comments)
  shares <- as_num(frame$num_shares)
  likes <- as_num(frame$num_likes)
  loves <- as_num(frame$num_loves)
  wows <- as_num(frame$num_wows)
  hahas <- as_num(frame$num_hahas)
  sads <- as_num(frame$num_sads)
  angrys <- as_num(frame$num_angrys)
  extras <- loves + wows + hahas + sads + angrys
  total <- pmax(1, reactions + comments + shares)
  data.frame(
    log_reactions = log1p(reactions),
    log_comments = log1p(comments),
    log_shares = log1p(shares),
    log_likes = log1p(likes),
    log_extras = log1p(extras),
    love_share = loves / pmax(1, reactions),
    comment_ratio = comments / total,
    share_ratio = shares / total,
    published_hour = as_num(frame$published_hour),
    published_month = as_num(frame$published_month),
    age_month = (as_num(frame$published_year) - 2012) * 12 + as_num(frame$published_month),
    behavior_propensity = as_num(frame$behavior_propensity),
    target_policy_weight = as_num(frame$target_policy_weight),
    stringsAsFactors = FALSE
  )
}

clean_cat <- function(values) {
  out <- as.character(values)
  out[is.na(out) | out == ""] <- "unknown"
  out
}

run_scorer <- function(input_dir, output_dir) {
  train <- read.csv(file.path(input_dir, "training_posts.csv"), stringsAsFactors = FALSE, check.names = FALSE)
  eval <- read.csv(file.path(input_dir, "evaluation_posts.csv"), stringsAsFactors = FALSE, check.names = FALSE)
  train_x <- make_features(train)
  eval_x <- make_features(eval)
  means <- vapply(train_x[features], mean, numeric(1))
  scales <- vapply(train_x[features], sd, numeric(1))
  scales[!is.finite(scales) | scales == 0] <- 1
  train_scaled <- sweep(sweep(as.matrix(train_x[features]), 2, means, "-"), 2, scales, "/")
  eval_scaled <- sweep(sweep(as.matrix(eval_x[features]), 2, means, "-"), 2, scales, "/")
  train_content <- clean_cat(train$logged_content_route)
  eval_content <- clean_cat(eval$logged_content_route)
  train_stratum <- clean_cat(train$priority_stratum)
  eval_stratum <- clean_cat(eval$priority_stratum)
  labels <- clean_cat(train$response_route)

  predict_one <- function(row_index) {
    differences <- sweep(train_scaled, 2, eval_scaled[row_index, ], "-")
    distances <- rowSums(differences * differences)
    distances <- distances + ifelse(train_content == eval_content[row_index], 0, 2.5)
    distances <- distances + ifelse(train_stratum == eval_stratum[row_index], 0, 1.5)
    nearest <- order(distances)
    nearest <- nearest[seq_len(min(5, length(nearest)))]
    counts <- setNames(rep(0.75, length(classes)), classes)
    for (neighbor in nearest) {
      route <- labels[neighbor]
      if (route %in% classes) {
        counts[route] <- counts[route] + 1 / (0.2 + distances[neighbor])
      }
    }
    counts / sum(counts)
  }

  prob_matrix <- t(vapply(seq_len(nrow(eval)), predict_one, numeric(length(classes))))
  out <- data.frame(post_id = eval$post_id, stringsAsFactors = FALSE)
  for (route in classes) {
    out[[paste0("prob_", route)]] <- prob_matrix[, route]
  }
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
  write.csv(out, file.path(output_dir, "response_route_probabilities.csv"), row.names = FALSE, quote = FALSE)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  run_scorer("/app/data", "/app/outputs")
} else if (length(args) == 2) {
  run_scorer(args[1], args[2])
} else {
  stop("usage: Rscript /app/score_response_routes.R <input_dir> <output_dir>")
}
RSCRIPT

cat > /app/analysis.R <<'RSCRIPT'
source("/app/score_response_routes.R", local = TRUE)
RSCRIPT

Rscript /app/analysis.R
