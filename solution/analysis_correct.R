suppressMessages({
  library(survival)
  library(jsonlite)
})

data_dir <- Sys.getenv("CAUSAL_DATA_DIR", "/app/data")

enrollment <- read.csv(file.path(data_dir, "enrollment.csv"), stringsAsFactors = FALSE)
followup <- read.csv(file.path(data_dir, "followup.csv"), stringsAsFactors = FALSE)

cohort <- merge(enrollment, followup, by = "patient_id")
cohort$arm <- ifelse(cohort$therapy == "newer", 1L, 0L)
cohort$event <- ifelse(cohort$outcome == "relapse", 1L, 0L)

# therapy uptake depends on the two flags and, nonlinearly, on the continuous baseline
# index; model that dependence and weight each patient by the inverse of the probability
# of the therapy they actually received, so the reweighted arms share the pre-treatment
# distribution
prop_fit <- glm(
  arm ~ stage_high + marker_high + baseline_index + I(baseline_index^2),
  data = cohort, family = binomial()
)
ps <- pmin(pmax(fitted(prop_fit), 0.02), 0.98)
cohort$w <- ifelse(cohort$arm == 1, 1 / ps, 1 / (1 - ps))

# weighted Kaplan-Meier survival at the plateau (after the last observed relapse); the
# plateau height is the long-term event-free fraction for the reweighted stratum
weighted_plateau <- function(df) {
  if (nrow(df) < 5) {
    return(NA_real_)
  }
  ord <- order(df$months_observed)
  t <- df$months_observed[ord]
  e <- df$event[ord]
  w <- df$w[ord]
  at_risk <- sum(w)
  surv <- 1
  i <- 1
  n <- length(t)
  while (i <= n) {
    tk <- t[i]
    j <- i
    d <- 0
    while (j <= n && t[j] == tk) {
      if (e[j] == 1) d <- d + w[j]
      j <- j + 1
    }
    if (d > 0 && at_risk > 0) surv <- surv * (1 - d / at_risk)
    at_risk <- at_risk - sum(w[i:(j - 1)])
    i <- j
  }
  surv
}

strata <- expand.grid(stage_high = c(0, 1), marker_high = c(0, 1))
n_total <- nrow(cohort)

standardized <- function(arm_value) {
  total <- 0
  for (i in seq_len(nrow(strata))) {
    f <- strata$stage_high[i]
    g <- strata$marker_high[i]
    in_stratum <- cohort$stage_high == f & cohort$marker_high == g
    weight <- sum(in_stratum) / n_total
    sub <- cohort[in_stratum & cohort$arm == arm_value, ]
    cure <- weighted_plateau(sub)
    if (!is.na(cure)) {
      total <- total + weight * cure
    }
  }
  total
}

estimate <- standardized(1) - standardized(0)

writeLines(toJSON(list(estimate = estimate), auto_unbox = TRUE, digits = 10), "/app/estimate.json")
