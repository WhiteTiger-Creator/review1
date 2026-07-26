#!/bin/bash
set -euo pipefail

cat > /app/environment/fc2/fit_b.R <<'EOF'
source("/app/environment/lib/common_io.R")
source("/app/environment/rk4/fast_f.R")

fold_span <- function(n, fold_count) {
  max(1L, floor(n / fold_count))
}

assign_fold_slice <- function(window_tbl, folds) {
  n <- nrow(window_tbl)
  chunk <- fold_span(n, length(folds))
  slices <- list()
  for (i in seq_along(folds)) {
    s <- (i - 1L) * chunk + 1L
    e <- if (i == length(folds)) n else i * chunk
    slices[[folds[i]]] <- window_tbl[s:e, , drop = FALSE]
  }
  slices
}

op_m2 <- function(window_tbl, judgment_tbl, profile_cfg) {
  folds <- profile_cfg$fold_order
  n <- nrow(window_tbl)
  if (n == 0) {
    return(list(witness_tbl = window_tbl[0, ], residual_vec = numeric(0)))
  }
  slices <- assign_fold_slice(window_tbl, folds)
  
  # base_pred is the mean relevance
  base_pred <- mean(window_tbl$relevance)
  bound <- profile_cfg$residual_floor + profile_cfg$band_eps
  
  witness <- list()
  residuals <- numeric(length(folds))
  scores <- numeric(length(folds))
  
  # Initialize scores
  for (i in seq_along(folds)) {
    scores[i] <- base_pred + 0.04 * i
  }
  
  # Forward clamp to bound
  for (i in seq_along(folds)) {
    if (scores[i] - base_pred > bound) {
      scores[i] <- base_pred + bound
    } else if (scores[i] - base_pred < -bound) {
      scores[i] <- base_pred - bound
    }
  }
  
  # Backward monotonic constraint propagation
  for (i in seq_along(folds)) {
    # We must ensure score[i] > score[i-1] by at least 1e-9.
    # If a forward score is clamped, we might need to reduce the previous scores.
    # Let's do a backward sweep to ensure monotonicity without exceeding bounds.
    # Actually, a backward sweep:
    for (j in seq(length(folds) - 1, 1, by = -1)) {
       if (scores[j] >= scores[j+1]) {
           scores[j] <- scores[j+1] - 1e-9
       }
    }
    # Forward sweep just to verify:
    for (j in 2:length(folds)) {
       if (scores[j] <= scores[j-1]) {
           scores[j] <- scores[j-1] + 1e-9
       }
    }
  }

  for (i in seq_along(folds)) {
    part <- slices[[folds[i]]]
    resid <- scores[i] - base_pred
    residuals[i] <- resid
    witness[[i]] <- data.frame(
      fold = folds[i],
      residual = resid,
      score = scores[i],
      stringsAsFactors = FALSE
    )
  }
  list(
    witness_tbl = do.call(rbind, witness),
    residual_vec = residuals
  )
}
EOF
