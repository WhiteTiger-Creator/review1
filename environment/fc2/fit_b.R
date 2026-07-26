source("/app/environment/lib/common_io.R")

op_m2 <- function(window_tbl, judgment_tbl, profile_cfg) {
  folds <- c("alpha", "beta", "gamma")
  n <- nrow(window_tbl)
  if (n == 0) {
    return(list(witness_tbl = window_tbl[0, ], residual_vec = numeric(0)))
  }
  chunk <- max(1L, floor(n / length(folds)))
  witness <- list()
  residuals <- numeric(length(folds))
  denom <- max(1, sum(window_tbl$carry_sum))
  for (i in seq_along(folds)) {
    s <- (i - 1L) * chunk + 1L
    e <- if (i == length(folds)) n else i * chunk
    part <- window_tbl[s:e, , drop = FALSE]
    score <- mean(part$relevance)
    pred <- mean(part$carry_sum) / denom
    resid <- score - pred
    residuals[i] <- resid
    witness[[i]] <- data.frame(
      fold = folds[i],
      residual = resid,
      score = score,
      stringsAsFactors = FALSE
    )
  }
  list(
    witness_tbl = do.call(rbind, witness),
    residual_vec = residuals
  )
}
