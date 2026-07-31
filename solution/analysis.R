#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

DATA_DIR <- "/app/data"
OUT_DIR <- "/app/outputs"
FEATURES <- c(
  "native_english_speaker",
  "course_instructor",
  "course_id",
  "summer_or_regular",
  "class_size"
)
CATEGORICAL <- FEATURES[1:4]
NUMERIC <- "class_size"
CLASSES <- c("eval_low", "eval_medium", "eval_high")
C_GRID <- c(0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30)
SEED <- 20260713L
ARTIFACTS <- c(
  "metrics.json",
  "candidate_results.csv",
  "fit_cv_results.csv",
  "fit_oof_predictions.csv",
  "fold_preprocessing_summary.csv",
  "predictions.csv",
  "validation_confusion_matrix.csv",
  "validation_class_report.csv",
  "validation_confidence_deciles.csv",
  "score_course_counterfactual.csv",
  "model_term_importance.csv",
  "preprocessing_summary.csv",
  "model_manifest.json"
)

round_value <- function(x, digits) {
  as.numeric(round(x, digits))
}

write_json_artifact <- function(value, name) {
  write_json(
    value,
    file.path(OUT_DIR, name),
    auto_unbox = TRUE,
    pretty = TRUE,
    digits = NA
  )
}

write_csv_artifact <- function(value, name) {
  write.csv(
    value,
    file.path(OUT_DIR, name),
    row.names = FALSE,
    quote = TRUE,
    na = ""
  )
}

mapped_category <- function(values) {
  mapped <- as.character(values)
  missing <- is.na(mapped) | trimws(mapped) == ""
  mapped[missing] <- "__missing__"
  mapped
}

missing_count <- function(values, categorical = FALSE) {
  if (categorical) {
    chars <- as.character(values)
    return(sum(is.na(chars) | trimws(chars) == ""))
  }
  sum(is.na(suppressWarnings(as.numeric(values))))
}

learn_preprocessor <- function(frame) {
  raw_numeric <- suppressWarnings(as.numeric(frame[[NUMERIC]]))
  center <- mean(raw_numeric, na.rm = TRUE)
  if (!is.finite(center)) {
    center <- 0
  }
  imputed <- raw_numeric
  imputed[is.na(imputed)] <- center
  scale_value <- stats::sd(imputed)
  if (!is.finite(scale_value) || scale_value == 0) {
    scale_value <- 1
  }

  categorical_levels <- lapply(CATEGORICAL, function(feature) {
    sort(unique(c(mapped_category(frame[[feature]]), "__missing__", "__other__")))
  })
  names(categorical_levels) <- CATEGORICAL

  terms <- character()
  for (feature in FEATURES) {
    if (feature == NUMERIC) {
      terms <- c(terms, feature)
    } else {
      encoded <- paste0(feature, "_", make.names(categorical_levels[[feature]]))
      terms <- c(terms, encoded)
    }
  }

  list(
    center = center,
    scale = scale_value,
    levels = categorical_levels,
    terms = terms
  )
}

transform_design <- function(frame, preprocessor) {
  columns <- vector("list", length(preprocessor$terms))
  names(columns) <- preprocessor$terms

  numeric_values <- suppressWarnings(as.numeric(frame[[NUMERIC]]))
  numeric_values[is.na(numeric_values)] <- preprocessor$center
  columns[[NUMERIC]] <- (numeric_values - preprocessor$center) / preprocessor$scale

  for (feature in CATEGORICAL) {
    mapped <- mapped_category(frame[[feature]])
    levels <- preprocessor$levels[[feature]]
    mapped[!(mapped %in% levels)] <- "__other__"
    for (level in levels) {
      term <- paste0(feature, "_", make.names(level))
      columns[[term]] <- as.numeric(mapped == level)
    }
  }

  matrix_value <- as.matrix(as.data.frame(columns, check.names = FALSE))
  storage.mode(matrix_value) <- "double"
  matrix_value[, preprocessor$terms, drop = FALSE]
}

class_weights <- function(labels) {
  counts <- table(factor(labels, levels = CLASSES))
  as.numeric(length(labels) / (length(CLASSES) * counts[labels]))
}

fit_model <- function(x, labels, c_value, seed_value) {
  set.seed(seed_value)
  model_frame <- as.data.frame(x, check.names = FALSE)
  model_frame$.target <- factor(labels, levels = CLASSES)
  suppressWarnings(
    nnet::multinom(
      .target ~ .,
      data = model_frame,
      weights = class_weights(labels),
      trace = FALSE,
      maxit = 1000,
      MaxNWts = 50000,
      decay = c_value
    )
  )
}

predict_probabilities <- function(model, x) {
  frame <- as.data.frame(x, check.names = FALSE)
  raw <- predict(model, newdata = frame, type = "probs")
  probabilities <- as.matrix(raw)
  if (is.null(colnames(probabilities))) {
    colnames(probabilities) <- CLASSES
  }
  probabilities <- probabilities[, CLASSES, drop = FALSE]
  probabilities / rowSums(probabilities)
}

predicted_classes <- function(probabilities) {
  CLASSES[max.col(probabilities, ties.method = "first")]
}

log_loss_components <- function(actual, probabilities) {
  positions <- match(actual, CLASSES)
  chosen <- probabilities[cbind(seq_along(actual), positions)]
  -log(pmax(chosen, 1e-15))
}

class_report <- function(actual, predicted, probabilities) {
  rows <- lapply(seq_along(CLASSES), function(index) {
    label <- CLASSES[index]
    actual_match <- actual == label
    predicted_match <- predicted == label
    support <- sum(actual_match)
    tp <- sum(actual_match & predicted_match)
    fp <- sum(!actual_match & predicted_match)
    fn <- sum(actual_match & !predicted_match)
    precision <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
    recall <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
    f1 <- if ((precision + recall) == 0) {
      0
    } else {
      2 * precision * recall / (precision + recall)
    }
    mean_probability <- if (support == 0) {
      0
    } else {
      mean(probabilities[actual_match, index])
    }
    data.frame(
      class = label,
      support = as.integer(support),
      precision = precision,
      recall = recall,
      f1 = f1,
      mean_probability = mean_probability,
      check.names = FALSE
    )
  })
  do.call(rbind, rows)
}

metric_bundle <- function(actual, probabilities) {
  predicted <- predicted_classes(probabilities)
  report <- class_report(actual, predicted, probabilities)
  list(
    macro_f1 = mean(report$f1),
    weighted_f1 = sum(report$f1 * report$support) / length(actual),
    balanced_accuracy = mean(report$recall),
    accuracy = mean(predicted == actual),
    log_loss = mean(log_loss_components(actual, probabilities))
  )
}

assign_folds <- function(frame) {
  fold <- integer(nrow(frame))
  for (label in CLASSES) {
    positions <- which(as.character(frame$evaluation_class) == label)
    positions <- positions[order(as.character(frame$row_id[positions]))]
    fold[positions] <- ((seq_along(positions) - 1L) %% 5L) + 1L
  }
  fold
}

confusion_frame <- function(actual, predicted) {
  rows <- vector("list", length(CLASSES) * length(CLASSES))
  cursor <- 1L
  for (actual_class in CLASSES) {
    for (predicted_class in CLASSES) {
      rows[[cursor]] <- data.frame(
        actual_class = actual_class,
        predicted_class = predicted_class,
        n = as.integer(sum(actual == actual_class & predicted == predicted_class)),
        check.names = FALSE
      )
      cursor <- cursor + 1L
    }
  }
  do.call(rbind, rows)
}

confidence_deciles <- function(row_ids, actual, probabilities) {
  predicted <- predicted_classes(probabilities)
  confidence <- apply(probabilities, 1, max)
  sorted_probabilities <- t(apply(probabilities, 1, sort, decreasing = TRUE))
  margin <- sorted_probabilities[, 1] - sorted_probabilities[, 2]
  loss <- log_loss_components(actual, probabilities)
  ordering <- order(-confidence, as.character(row_ids))
  assigned <- integer(length(actual))
  assigned[ordering] <- floor((seq_along(ordering) - 1) * 10 / length(ordering)) + 1L

  rows <- lapply(1:10, function(decile) {
    selected <- assigned == decile
    count <- sum(selected)
    data.frame(
      decile = as.integer(decile),
      row_count = as.integer(count),
      accuracy = if (count == 0) 0 else mean(predicted[selected] == actual[selected]),
      mean_confidence = if (count == 0) 0 else mean(confidence[selected]),
      mean_margin = if (count == 0) 0 else mean(margin[selected]),
      mean_log_loss_component = if (count == 0) 0 else mean(loss[selected]),
      check.names = FALSE
    )
  })
  do.call(rbind, rows)
}

preprocessing_summary <- function(preprocessor, fit, validation, score) {
  rows <- lapply(FEATURES, function(feature) {
    categorical <- feature %in% CATEGORICAL
    data.frame(
      feature = feature,
      feature_type = if (categorical) "categorical" else "numeric",
      fit_missing_count = as.integer(missing_count(fit[[feature]], categorical)),
      validation_missing_count = as.integer(
        missing_count(validation[[feature]], categorical)
      ),
      score_missing_count = as.integer(missing_count(score[[feature]], categorical)),
      fit_center = if (categorical) 0 else preprocessor$center,
      fit_sample_sd = if (categorical) 1 else preprocessor$scale,
      level_count = if (categorical) {
        as.integer(length(preprocessor$levels[[feature]]))
      } else {
        0L
      },
      check.names = FALSE
    )
  })
  do.call(rbind, rows)
}

term_importance <- function(model, design_terms) {
  coefficient_matrix <- as.matrix(coef(model))
  non_intercept <- coefficient_matrix[
    ,
    setdiff(colnames(coefficient_matrix), "(Intercept)"),
    drop = FALSE
  ]
  non_intercept <- non_intercept[, design_terms, drop = FALSE]

  norms <- numeric(length(FEATURES))
  maximums <- numeric(length(FEATURES))
  counts <- integer(length(FEATURES))
  for (index in seq_along(FEATURES)) {
    feature <- FEATURES[index]
    terms <- if (feature == NUMERIC) {
      feature
    } else {
      design_terms[startsWith(design_terms, paste0(feature, "_"))]
    }
    values <- non_intercept[, terms, drop = FALSE]
    norms[index] <- sqrt(sum(values^2))
    maximums[index] <- if (length(values) == 0) 0 else max(abs(values))
    counts[index] <- length(terms)
  }
  total <- sum(norms)
  data.frame(
    feature = FEATURES,
    design_term_count = as.integer(counts),
    l2_norm = round_value(norms, 8),
    normalized_importance = round_value(if (total == 0) 0 else norms / total, 8),
    max_abs_coefficient = round_value(maximums, 8),
    check.names = FALSE
  )
}

main <- function() {
  dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)
  existing <- list.files(OUT_DIR, full.names = TRUE, all.files = TRUE)
  existing <- existing[!(basename(existing) %in% c(".", ".."))]
  if (length(existing) > 0) {
    unlink(existing, recursive = TRUE, force = TRUE)
  }

  train <- read.csv(
    file.path(DATA_DIR, "train.csv"),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
  score <- read.csv(
    file.path(DATA_DIR, "score.csv"),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
  fit <- train[train$split_role == "fit", , drop = FALSE]
  validation <- train[train$split_role == "validation", , drop = FALSE]
  fit$evaluation_class <- factor(fit$evaluation_class, levels = CLASSES)
  validation$evaluation_class <- factor(validation$evaluation_class, levels = CLASSES)
  fold_ids <- assign_folds(fit)

  cv_rows <- list()
  candidate_probabilities <- vector("list", length(C_GRID))
  candidate_fold_preprocessors <- vector("list", length(C_GRID))
  candidate_metrics <- vector("list", length(C_GRID))
  cursor <- 1L

  for (candidate_index in seq_along(C_GRID)) {
    c_value <- C_GRID[candidate_index]
    oof_probability <- matrix(
      NA_real_,
      nrow = nrow(fit),
      ncol = length(CLASSES),
      dimnames = list(NULL, CLASSES)
    )
    fold_preprocessors <- vector("list", 5)
    losses <- numeric(5)
    macro_scores <- numeric(5)

    for (fold_id in 1:5) {
      training_positions <- which(fold_ids != fold_id)
      holdout_positions <- which(fold_ids == fold_id)
      training_frame <- fit[training_positions, , drop = FALSE]
      holdout_frame <- fit[holdout_positions, , drop = FALSE]
      preprocessor <- learn_preprocessor(training_frame)
      training_x <- transform_design(training_frame, preprocessor)
      holdout_x <- transform_design(holdout_frame, preprocessor)
      model <- fit_model(
        training_x,
        as.character(training_frame$evaluation_class),
        c_value,
        SEED + 100L * candidate_index + fold_id
      )
      holdout_probability <- predict_probabilities(model, holdout_x)
      oof_probability[holdout_positions, ] <- holdout_probability
      metrics <- metric_bundle(
        as.character(holdout_frame$evaluation_class),
        holdout_probability
      )
      losses[fold_id] <- metrics$log_loss
      macro_scores[fold_id] <- metrics$macro_f1
      fold_preprocessors[[fold_id]] <- preprocessor
      cv_rows[[cursor]] <- data.frame(
        candidate_c = c_value,
        fold_id = as.integer(fold_id),
        training_rows = as.integer(length(training_positions)),
        holdout_rows = as.integer(length(holdout_positions)),
        holdout_log_loss = metrics$log_loss,
        holdout_macro_f1 = metrics$macro_f1,
        holdout_accuracy = metrics$accuracy,
        check.names = FALSE
      )
      cursor <- cursor + 1L
    }

    candidate_probabilities[[candidate_index]] <- oof_probability
    candidate_fold_preprocessors[[candidate_index]] <- fold_preprocessors
    candidate_metrics[[candidate_index]] <- list(
      mean_log_loss = mean(losses),
      sd_log_loss = stats::sd(losses),
      mean_macro_f1 = mean(macro_scores)
    )
  }

  mean_losses <- vapply(candidate_metrics, `[[`, numeric(1), "mean_log_loss")
  selected_index <- which(mean_losses <= min(mean_losses) + 1e-10)[1]
  selected_c <- C_GRID[selected_index]

  candidate_results <- do.call(
    rbind,
    lapply(seq_along(C_GRID), function(index) {
      data.frame(
        candidate_c = C_GRID[index],
        cv_mean_log_loss = round_value(
          candidate_metrics[[index]]$mean_log_loss,
          6
        ),
        cv_log_loss_sd = round_value(
          candidate_metrics[[index]]$sd_log_loss,
          6
        ),
        cv_mean_macro_f1 = round_value(
          candidate_metrics[[index]]$mean_macro_f1,
          6
        ),
        is_selected = as.integer(index == selected_index),
        check.names = FALSE
      )
    })
  )

  fit_cv_results <- do.call(rbind, cv_rows)
  metric_columns <- c("holdout_log_loss", "holdout_macro_f1", "holdout_accuracy")
  fit_cv_results[metric_columns] <- lapply(
    fit_cv_results[metric_columns],
    round_value,
    digits = 6
  )

  selected_oof <- candidate_probabilities[[selected_index]]
  selected_oof_classes <- predicted_classes(selected_oof)
  fit_order <- order(as.character(fit$row_id))
  fit_oof_predictions <- data.frame(
    row_id = as.character(fit$row_id[fit_order]),
    fold_id = as.integer(fold_ids[fit_order]),
    actual_class = as.character(fit$evaluation_class[fit_order]),
    predicted_class = selected_oof_classes[fit_order],
    prob_eval_low = round_value(selected_oof[fit_order, 1], 8),
    prob_eval_medium = round_value(selected_oof[fit_order, 2], 8),
    prob_eval_high = round_value(selected_oof[fit_order, 3], 8),
    log_loss_component = round_value(
      log_loss_components(as.character(fit$evaluation_class), selected_oof)[
        fit_order
      ],
      8
    ),
    is_correct = as.integer(
      selected_oof_classes[fit_order] ==
        as.character(fit$evaluation_class[fit_order])
    ),
    check.names = FALSE
  )

  selected_preprocessors <- candidate_fold_preprocessors[[selected_index]]
  fold_preprocessing_summary <- do.call(
    rbind,
    lapply(1:5, function(fold_id) {
      preprocessor <- selected_preprocessors[[fold_id]]
      training_positions <- which(fold_ids != fold_id)
      holdout_positions <- which(fold_ids == fold_id)
      data.frame(
        fold_id = as.integer(fold_id),
        training_rows = as.integer(length(training_positions)),
        holdout_rows = as.integer(length(holdout_positions)),
        class_size_missing_count = as.integer(
          missing_count(fit$class_size[training_positions])
        ),
        class_size_center = round_value(preprocessor$center, 8),
        class_size_sample_sd = round_value(preprocessor$scale, 8),
        instructor_level_count = as.integer(
          length(preprocessor$levels$course_instructor)
        ),
        course_level_count = as.integer(length(preprocessor$levels$course_id)),
        check.names = FALSE
      )
    })
  )

  final_preprocessor <- learn_preprocessor(fit)
  fit_x <- transform_design(fit, final_preprocessor)
  validation_x <- transform_design(validation, final_preprocessor)
  score_x <- transform_design(score, final_preprocessor)
  final_model <- fit_model(
    fit_x,
    as.character(fit$evaluation_class),
    selected_c,
    SEED + 9000L + selected_index
  )
  validation_probability <- predict_probabilities(final_model, validation_x)
  score_probability <- predict_probabilities(final_model, score_x)
  validation_classes <- predicted_classes(validation_probability)
  score_classes <- predicted_classes(score_probability)
  validation_metrics <- metric_bundle(
    as.character(validation$evaluation_class),
    validation_probability
  )
  oof_metrics <- metric_bundle(
    as.character(fit$evaluation_class),
    selected_oof
  )

  score_order <- order(as.character(score$row_id))
  predictions <- data.frame(
    row_id = as.character(score$row_id[score_order]),
    predicted_class = score_classes[score_order],
    prob_eval_low = round_value(score_probability[score_order, 1], 8),
    prob_eval_medium = round_value(score_probability[score_order, 2], 8),
    prob_eval_high = round_value(score_probability[score_order, 3], 8),
    check.names = FALSE
  )

  validation_report <- class_report(
    as.character(validation$evaluation_class),
    validation_classes,
    validation_probability
  )
  for (column in c("precision", "recall", "f1", "mean_probability")) {
    validation_report[[column]] <- round_value(validation_report[[column]], 6)
  }

  deciles <- confidence_deciles(
    validation$row_id,
    as.character(validation$evaluation_class),
    validation_probability
  )
  for (column in c(
    "accuracy",
    "mean_confidence",
    "mean_margin",
    "mean_log_loss_component"
  )) {
    deciles[[column]] <- round_value(deciles[[column]], 6)
  }

  counterfactual_rows <- lapply(
    final_preprocessor$levels$course_instructor,
    function(level) {
      changed_score <- score
      changed_score$course_instructor <- level
      changed_x <- transform_design(changed_score, final_preprocessor)
      changed_probability <- predict_probabilities(final_model, changed_x)
      changed_classes <- predicted_classes(changed_probability)
      data.frame(
        course_instructor_level = level,
        encoded_column = paste0("course_instructor_", make.names(level)),
        predicted_eval_low_count = as.integer(
          sum(changed_classes == "eval_low")
        ),
        predicted_eval_medium_count = as.integer(
          sum(changed_classes == "eval_medium")
        ),
        predicted_eval_high_count = as.integer(
          sum(changed_classes == "eval_high")
        ),
        changed_class_count = as.integer(sum(changed_classes != score_classes)),
        mean_prob_eval_low = round_value(mean(changed_probability[, 1]), 6),
        mean_prob_eval_medium = round_value(mean(changed_probability[, 2]), 6),
        mean_prob_eval_high = round_value(mean(changed_probability[, 3]), 6),
        mean_total_variation = round_value(
          mean(rowSums(abs(changed_probability - score_probability)) / 2),
          6
        ),
        check.names = FALSE
      )
    }
  )
  score_course_counterfactual <- do.call(rbind, counterfactual_rows)

  final_preprocessing_summary <- preprocessing_summary(
    final_preprocessor,
    fit,
    validation,
    score
  )
  final_preprocessing_summary$fit_center <- round_value(
    final_preprocessing_summary$fit_center,
    8
  )
  final_preprocessing_summary$fit_sample_sd <- round_value(
    final_preprocessing_summary$fit_sample_sd,
    8
  )

  metrics <- list(
    task_name = "tae-multiclass-cv-audit",
    n_fit = as.integer(nrow(fit)),
    n_validation = as.integer(nrow(validation)),
    n_score = as.integer(nrow(score)),
    classes = CLASSES,
    selected_c = round_value(selected_c, 6),
    selected_cv_mean_log_loss = round_value(
      candidate_metrics[[selected_index]]$mean_log_loss,
      6
    ),
    selected_cv_log_loss_sd = round_value(
      candidate_metrics[[selected_index]]$sd_log_loss,
      6
    ),
    validation_macro_f1 = round_value(validation_metrics$macro_f1, 6),
    validation_weighted_f1 = round_value(validation_metrics$weighted_f1, 6),
    validation_balanced_accuracy = round_value(
      validation_metrics$balanced_accuracy,
      6
    ),
    validation_accuracy = round_value(validation_metrics$accuracy, 6),
    validation_log_loss = round_value(validation_metrics$log_loss, 6),
    fit_oof_macro_f1 = round_value(oof_metrics$macro_f1, 6),
    fit_oof_log_loss = round_value(oof_metrics$log_loss, 6)
  )

  manifest <- list(
    task_name = "tae-multiclass-cv-audit",
    feature_columns = FEATURES,
    categorical_columns = CATEGORICAL,
    numeric_columns = I(NUMERIC),
    excluded_columns = c("row_id", "split_role", "evaluation_class"),
    fit_rows = as.integer(nrow(fit)),
    validation_rows = as.integer(nrow(validation)),
    score_rows = as.integer(nrow(score)),
    candidate_grid = C_GRID,
    selected_c = selected_c,
    cv_folds = 5L,
    random_state = SEED,
    class_order = CLASSES,
    model_family = "class_weighted_multinomial_ridge",
    source_dataset = "UCI Teaching Assistant Evaluation Dataset",
    design_columns = final_preprocessor$terms,
    artifact_files = ARTIFACTS
  )

  write_json_artifact(metrics, "metrics.json")
  write_csv_artifact(candidate_results, "candidate_results.csv")
  write_csv_artifact(fit_cv_results, "fit_cv_results.csv")
  write_csv_artifact(fit_oof_predictions, "fit_oof_predictions.csv")
  write_csv_artifact(
    fold_preprocessing_summary,
    "fold_preprocessing_summary.csv"
  )
  write_csv_artifact(predictions, "predictions.csv")
  write_csv_artifact(
    confusion_frame(
      as.character(validation$evaluation_class),
      validation_classes
    ),
    "validation_confusion_matrix.csv"
  )
  write_csv_artifact(validation_report, "validation_class_report.csv")
  write_csv_artifact(deciles, "validation_confidence_deciles.csv")
  write_csv_artifact(
    score_course_counterfactual,
    "score_course_counterfactual.csv"
  )
  write_csv_artifact(
    term_importance(final_model, final_preprocessor$terms),
    "model_term_importance.csv"
  )
  write_csv_artifact(
    final_preprocessing_summary,
    "preprocessing_summary.csv"
  )
  write_json_artifact(manifest, "model_manifest.json")
}

main()
