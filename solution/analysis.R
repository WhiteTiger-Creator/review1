suppressPackageStartupMessages(library(jsonlite))

CONFIG_DIR <- Sys.getenv("CONFIG_DIR", "/app/config")
kv <- read.csv(file.path(CONFIG_DIR, "model_config.csv"), stringsAsFactors = FALSE)
cfg <- as.list(stats::setNames(as.character(kv$value), kv$key))
cost_kv <- read.csv(file.path(CONFIG_DIR, "costs.csv"), stringsAsFactors = FALSE)
cost_of <- as.list(stats::setNames(as.numeric(cost_kv$value), cost_kv$key))

DATA_DIR <- Sys.getenv("DATA_DIR", "/app/data")
DATA_PATH <- Sys.getenv("DATA_PATH", file.path(DATA_DIR, cfg$data_file))
OUT_DIR <- Sys.getenv("OUT_DIR", Sys.getenv("OUTPUT_DIR", "/app/outputs"))
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

stopifnot(cfg$task_kind == "binary")

BLANK_TOKENS <- c("", "NA", "NaN", "nan", "null", "?")
roles <- read.csv(file.path(CONFIG_DIR, "feature_roles.csv"), stringsAsFactors = FALSE)
tbl <- read.csv(DATA_PATH, stringsAsFactors = FALSE, na.strings = BLANK_TOKENS,
                check.names = FALSE)

id_col <- cfg$id_column
split_col <- cfg$split_column
target_col <- cfg$target_column
group_col <- cfg$group_column
classes <- strsplit(cfg$class_order, "|", fixed = TRUE)[[1]]
pos_class <- cfg$positive_class
neg_class <- setdiff(classes, pos_class)[[1]]
k_grid <- as.integer(strsplit(cfg$k_grid, "|", fixed = TRUE)[[1]])
threshold_grid <- as.numeric(strsplit(cfg$threshold_grid, "|", fixed = TRUE)[[1]])

feature_names <- roles$feature[roles$role == "feature"]
feature_types <- roles$data_type[roles$role == "feature"]

as_num <- function(x) {
  y <- suppressWarnings(as.numeric(x))
  y[!is.finite(y)] <- NA_real_
  y
}

as_cat <- function(x) {
  y <- as.character(x)
  y[is.na(y) | y %in% BLANK_TOKENS] <- "__missing__"
  y
}

tidy_token <- function(x) {
  y <- tolower(gsub("[^A-Za-z0-9]", "_", x))
  gsub("^_+|_+$", "", y)
}

learn_design <- function(frame) {
  design <- list()
  for (i in seq_along(feature_names)) {
    nm <- feature_names[[i]]
    if (feature_types[[i]] == "numeric") {
      v <- as_num(frame[[nm]])
      mid <- stats::median(v, na.rm = TRUE)
      if (!is.finite(mid)) mid <- 0
      v[is.na(v)] <- mid
      ctr <- mean(v)
      spr <- stats::sd(v)
      if (!is.finite(spr) || spr < 1e-9) spr <- 1
      design[[nm]] <- list(kind = "numeric", mid = mid, ctr = ctr, spr = spr)
    } else {
      lv <- sort(unique(as_cat(frame[[nm]])))
      lv <- unique(c(lv, "__missing__", "__other__"))
      design[[nm]] <- list(kind = "categorical", levels = lv)
    }
  }
  design
}

render_design <- function(frame, design) {
  blocks <- list()
  for (nm in names(design)) {
    d <- design[[nm]]
    if (d$kind == "numeric") {
      v <- as_num(frame[[nm]])
      v[is.na(v)] <- d$mid
      blocks[[length(blocks) + 1L]] <- matrix((v - d$ctr) / d$spr, ncol = 1)
    } else {
      v <- as_cat(frame[[nm]])
      v[!(v %in% d$levels)] <- "__other__"
      m <- matrix(0, nrow = nrow(frame), ncol = length(d$levels))
      for (j in seq_along(d$levels)) {
        m[, j] <- as.numeric(v == d$levels[[j]])
      }
      blocks[[length(blocks) + 1L]] <- m
    }
  }
  do.call(cbind, blocks)
}

weighted_positive_share <- function(ref_x, ref_is_pos, query_x, k) {
  n <- nrow(query_x)
  kk <- min(k, nrow(ref_x))
  share <- numeric(n)
  for (i in seq_len(n)) {
    delta <- sweep(ref_x, 2, query_x[i, ], "-")
    d <- sqrt(rowSums(delta * delta))
    pick <- order(d)[seq_len(kk)]
    w <- 1 / (d[pick] + 1e-6)
    total <- sum(w)
    share[i] <- if (total <= 0) 0.5 else sum(w[ref_is_pos[pick]]) / total
  }
  round(share, 6)
}

loo_positive_share <- function(ref_x, ref_is_pos, k) {
  n <- nrow(ref_x)
  kk <- min(k, n - 1L)
  share <- numeric(n)
  for (i in seq_len(n)) {
    delta <- sweep(ref_x, 2, ref_x[i, ], "-")
    d <- sqrt(rowSums(delta * delta))
    d[[i]] <- Inf
    pick <- order(d)[seq_len(kk)]
    w <- 1 / (d[pick] + 1e-6)
    total <- sum(w)
    share[[i]] <- if (total <= 0) 0.5 else sum(w[ref_is_pos[pick]]) / total
  }
  round(share, 6)
}

closest_reference <- function(ref_x, ref_ids, query_x) {
  n <- nrow(query_x)
  hit_id <- ref_ids[seq_len(n)]
  hit_d <- numeric(n)
  for (i in seq_len(n)) {
    delta <- sweep(ref_x, 2, query_x[i, ], "-")
    d <- sqrt(rowSums(delta * delta))
    first <- order(d)[[1]]
    hit_id[[i]] <- ref_ids[[first]]
    hit_d[[i]] <- d[[first]]
  }
  list(id = hit_id, distance = round(hit_d, 6))
}

macro_f1_score <- function(actual, predicted) {
  per_class <- numeric(length(classes))
  for (i in seq_along(classes)) {
    cls <- classes[[i]]
    tp <- sum(actual == cls & predicted == cls)
    fp <- sum(actual != cls & predicted == cls)
    fn <- sum(actual == cls & predicted != cls)
    prc <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
    rec <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
    per_class[[i]] <- if ((prc + rec) == 0) 0 else 2 * prc * rec / (prc + rec)
  }
  mean(per_class)
}

fit_rows <- tbl[tbl[[split_col]] == "fit", , drop = FALSE]
val_rows <- tbl[tbl[[split_col]] == "validation", , drop = FALSE]
test_rows <- tbl[tbl[[split_col]] == "test", , drop = FALSE]

design <- learn_design(fit_rows)
fit_x <- render_design(fit_rows, design)
val_x <- render_design(val_rows, design)
fit_is_pos <- as.character(fit_rows[[target_col]]) == pos_class
val_actual <- as.character(val_rows[[target_col]])

selection_rows <- list()
best_k <- k_grid[[1]]
best_f1 <- -Inf
for (k in k_grid) {
  p6 <- weighted_positive_share(fit_x, fit_is_pos, val_x, k)
  lab <- ifelse(p6 >= 0.5, pos_class, neg_class)
  f1 <- macro_f1_score(val_actual, lab)
  selection_rows[[length(selection_rows) + 1L]] <-
    data.frame(candidate_k = k, validation_macro_f1 = round(f1, 6))
  if (f1 > best_f1 + 1e-12) {
    best_f1 <- f1
    best_k <- k
  }
}

val_p6 <- weighted_positive_share(fit_x, fit_is_pos, val_x, best_k)

val_group_chr <- as.character(val_rows[[group_col]])
group_names <- sort(unique(val_group_chr))
threshold_rows <- list()
best_t <- threshold_grid[[1]]
best_worst <- Inf
best_cost <- Inf
for (t in threshold_grid) {
  fp <- sum(val_actual == neg_class & val_p6 >= t)
  fn <- sum(val_actual == pos_class & val_p6 < t)
  cost <- (cost_of$false_positive_cost * fp + cost_of$false_negative_cost * fn) / nrow(val_rows)
  worst <- -Inf
  for (g in group_names) {
    inside <- val_group_chr == g
    gfp <- sum(val_actual[inside] == neg_class & val_p6[inside] >= t)
    gfn <- sum(val_actual[inside] == pos_class & val_p6[inside] < t)
    gcost <- (cost_of$false_positive_cost * gfp + cost_of$false_negative_cost * gfn) / sum(inside)
    if (gcost > worst) worst <- gcost
  }
  threshold_rows[[length(threshold_rows) + 1L]] <- data.frame(
    threshold = t, false_positives = fp, false_negatives = fn,
    expected_cost = round(cost, 6), worst_group_cost = round(worst, 6))
  if (worst < best_worst - 1e-12) {
    best_worst <- worst
    best_t <- t
    best_cost <- cost
  }
}

val_label <- ifelse(val_p6 >= best_t, pos_class, neg_class)

# Fit-rows-only design (contractual): scoring for test grows the NEIGHBOUR REFERENCE
# SET to fit+validation, but REUSES the design (imputation medians, scaling means/sds,
# level sets) learned from fit rows only -- it never re-learns on fit+validation.
ref_rows <- tbl[tbl[[split_col]] %in% c("fit", "validation"), , drop = FALSE]
ref_x <- render_design(ref_rows, design)
ref_is_pos <- as.character(ref_rows[[target_col]]) == pos_class
test_x <- render_design(test_rows, design)
test_p6 <- weighted_positive_share(ref_x, ref_is_pos, test_x, best_k)
test_label <- ifelse(test_p6 >= best_t, pos_class, neg_class)

prob_neg_col <- paste0("prob_", tidy_token(neg_class))
prob_pos_col <- paste0("prob_", tidy_token(pos_class))

val_out <- data.frame(
  a = val_rows[[id_col]],
  b = val_actual,
  c = val_label,
  d = as.integer(val_actual == val_label),
  e = as.character(val_rows[[group_col]]),
  f = round(1 - val_p6, 6),
  g = val_p6,
  stringsAsFactors = FALSE)
names(val_out) <- c(id_col, "actual", "pred_label", "correct", group_col,
                    prob_neg_col, prob_pos_col)
val_out <- val_out[order(val_out[[id_col]]), , drop = FALSE]
write.csv(val_out, file.path(OUT_DIR, "validation_predictions.csv"),
          row.names = FALSE, quote = FALSE)

test_out <- data.frame(
  a = test_rows[[id_col]],
  b = test_label,
  c = as.character(test_rows[[group_col]]),
  d = round(1 - test_p6, 6),
  e = test_p6,
  stringsAsFactors = FALSE)
names(test_out) <- c(id_col, "pred_label", group_col, prob_neg_col, prob_pos_col)
test_out <- test_out[order(test_out[[id_col]]), , drop = FALSE]
write.csv(test_out, file.path(OUT_DIR, "predictions.csv"),
          row.names = FALSE, quote = FALSE)

selection_report <- do.call(rbind, selection_rows)
selection_report$selected <- as.integer(selection_report$candidate_k == best_k)
write.csv(selection_report, file.path(OUT_DIR, "selection_report.csv"),
          row.names = FALSE, quote = FALSE)

threshold_report <- do.call(rbind, threshold_rows)
threshold_report$selected <- as.integer(abs(threshold_report$threshold - best_t) < 1e-12)
write.csv(threshold_report, file.path(OUT_DIR, "threshold_report.csv"),
          row.names = FALSE, quote = FALSE)

cells <- list()
for (a in classes) {
  for (p in classes) {
    cells[[length(cells) + 1L]] <- data.frame(
      actual = a, predicted = p, count = sum(val_actual == a & val_label == p))
  }
}
write.csv(do.call(rbind, cells), file.path(OUT_DIR, "confusion_matrix.csv"),
          row.names = FALSE, quote = FALSE)

per_class <- list()
for (cls in classes) {
  tp <- sum(val_actual == cls & val_label == cls)
  fp <- sum(val_actual != cls & val_label == cls)
  fn <- sum(val_actual == cls & val_label != cls)
  prc <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
  rec <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
  f1 <- if ((prc + rec) == 0) 0 else 2 * prc * rec / (prc + rec)
  per_class[[length(per_class) + 1L]] <- data.frame(
    class = cls, precision = round(prc, 6), recall = round(rec, 6),
    f1 = round(f1, 6), support = sum(val_actual == cls))
}
write.csv(do.call(rbind, per_class), file.path(OUT_DIR, "class_metrics.csv"),
          row.names = FALSE, quote = FALSE)

bin_idx <- pmin(4, floor(val_p6 * 5))
bin_rows <- list()
for (b in 0:4) {
  inside <- bin_idx == b
  cnt <- sum(inside)
  bin_rows[[length(bin_rows) + 1L]] <- data.frame(
    bin_low = b / 5,
    bin_high = (b + 1) / 5,
    count = cnt,
    mean_predicted = if (cnt > 0) round(mean(val_p6[inside]), 6) else 0,
    observed_rate = if (cnt > 0) round(mean(val_actual[inside] == pos_class), 6) else 0)
}
write.csv(do.call(rbind, bin_rows), file.path(OUT_DIR, "calibration_bins.csv"),
          row.names = FALSE, quote = FALSE)

val_groups <- as.character(val_rows[[group_col]])
ordered_val_groups <- val_groups[order(val_rows[[id_col]])]
ordered_actual <- val_actual[order(val_rows[[id_col]])]
ordered_label <- val_label[order(val_rows[[id_col]])]
group_rows <- list()
for (g in sort(unique(val_groups))) {
  inside <- ordered_val_groups == g
  group_rows[[length(group_rows) + 1L]] <- data.frame(
    group_value = g,
    n_validation = sum(inside),
    accuracy = round(mean(ordered_label[inside] == ordered_actual[inside]), 6))
}
write.csv(do.call(rbind, group_rows), file.path(OUT_DIR, "group_error_report.csv"),
          row.names = FALSE, quote = FALSE)

summary_rows <- list()
for (i in seq_along(feature_names)) {
  nm <- feature_names[[i]]
  summary_rows[[length(summary_rows) + 1L]] <- data.frame(
    feature = nm,
    data_type = feature_types[[i]],
    missing_fit = sum(is.na(fit_rows[[nm]])),
    missing_validation = sum(is.na(val_rows[[nm]])),
    missing_test = sum(is.na(test_rows[[nm]])))
}
write.csv(do.call(rbind, summary_rows), file.path(OUT_DIR, "feature_summary.csv"),
          row.names = FALSE, quote = FALSE)

test_order <- order(test_rows[[id_col]])
show_n <- min(50L, nrow(test_rows))
lead_x <- test_x[test_order[seq_len(show_n)], , drop = FALSE]
lead_ids <- test_rows[[id_col]][test_order[seq_len(show_n)]]
closest <- closest_reference(ref_x, ref_rows[[id_col]], lead_x)
evidence <- data.frame(a = lead_ids, nearest_reference_id = closest$id,
                       nearest_distance = closest$distance)
names(evidence)[[1]] <- id_col
write.csv(evidence, file.path(OUT_DIR, "neighbor_evidence.csv"),
          row.names = FALSE, quote = FALSE)

fit_loo_p6 <- loo_positive_share(fit_x, fit_is_pos, best_k)
sorted_loo <- sort(fit_loo_p6)
n_fit_rows <- length(sorted_loo)
edges <- numeric(4)
for (j in 1:4) edges[[j]] <- sorted_loo[[ceiling(j * n_fit_rows / 5)]]
val_bins <- vapply(val_p6, function(p) 1L + sum(edges < p), integer(1))
fit_cal_rows <- list()
for (b in 1:5) {
  inside <- val_bins == b
  cnt <- sum(inside)
  fit_cal_rows[[b]] <- data.frame(
    bin = b,
    lower_edge = if (b == 1) 0 else edges[[b - 1]],
    upper_edge = if (b == 5) 1 else edges[[b]],
    count = cnt,
    mean_predicted = if (cnt > 0) round(mean(val_p6[inside]), 6) else 0,
    observed_rate = if (cnt > 0) round(mean(val_actual[inside] == pos_class), 6) else 0)
}
write.csv(do.call(rbind, fit_cal_rows),
          file.path(OUT_DIR, "fit_reference_calibration.csv"),
          row.names = FALSE, quote = FALSE)

detail_n <- min(40L, nrow(test_rows))
detail_idx <- test_order[seq_len(detail_n)]
all_ref_ids <- ref_rows[[id_col]]
kk_detail <- min(best_k, nrow(ref_x))
detail_rows <- list()
for (i in detail_idx) {
  delta <- sweep(ref_x, 2, test_x[i, ], "-")
  d <- sqrt(rowSums(delta * delta))
  d6 <- round(d, 6)
  pick <- order(d6, all_ref_ids)[seq_len(kk_detail)]
  w <- 1 / (d[pick] + 1e-6)
  detail_rows[[length(detail_rows) + 1L]] <- data.frame(
    a = test_rows[[id_col]][[i]],
    neighbor_rank = seq_len(kk_detail),
    neighbor_id = all_ref_ids[pick],
    distance = d6[pick],
    weight_share = round(w / sum(w), 6))
}
detail <- do.call(rbind, detail_rows)
names(detail)[[1]] <- id_col
write.csv(detail, file.path(OUT_DIR, "neighbor_detail.csv"),
          row.names = FALSE, quote = FALSE)

fit_ids <- fit_rows[[id_col]]
fit_id_order <- order(fit_ids)
stride <- max(1L, n_fit_rows %/% 12L)
audit_pos <- 1L + stride * 0:11
audit_pos <- audit_pos[audit_pos <= n_fit_rows]
audit_idx <- fit_id_order[audit_pos]
audit_p6 <- fit_loo_p6[audit_idx]
audit_actual <- as.character(fit_rows[[target_col]])[audit_idx]
audit_label <- ifelse(audit_p6 >= best_t, pos_class, neg_class)
audit <- data.frame(
  a = fit_ids[audit_idx],
  actual = audit_actual,
  loo_positive_prob = audit_p6,
  loo_pred_label = audit_label,
  loo_correct = as.integer(audit_label == audit_actual))
names(audit)[[1]] <- id_col
write.csv(audit, file.path(OUT_DIR, "loo_audit.csv"),
          row.names = FALSE, quote = FALSE)

acc <- mean(val_actual == val_label)
metrics <- list(
  task_kind = cfg$task_kind,
  target_column = target_col,
  selected_k = as.integer(best_k),
  operating_threshold = best_t,
  n_fit = nrow(fit_rows),
  n_validation = nrow(val_rows),
  n_test = nrow(test_rows),
  validation_accuracy = round(acc, 6),
  validation_macro_f1 = round(macro_f1_score(val_actual, val_label), 6),
  validation_expected_cost = round(best_cost, 6))
write_json(metrics, file.path(OUT_DIR, "metrics.json"),
           auto_unbox = TRUE, pretty = TRUE, digits = NA)
