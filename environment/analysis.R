suppressMessages({
  library(jsonlite)
})

# starting scaffold: reads the records and writes a placeholder estimate so the
# output contract is satisfied. Replace the body with the real analysis.

data_dir <- Sys.getenv("CAUSAL_DATA_DIR", "/app/data")

enrollment <- read.csv(file.path(data_dir, "enrollment.csv"), stringsAsFactors = FALSE)
followup <- read.csv(file.path(data_dir, "followup.csv"), stringsAsFactors = FALSE)

cohort <- merge(enrollment, followup, by = "patient_id")
cohort$arm <- ifelse(cohort$therapy == "newer", 1L, 0L)
cohort$event_free <- ifelse(cohort$outcome == "relapse", 0L, 1L)

newer <- mean(cohort$event_free[cohort$arm == 1])
standard <- mean(cohort$event_free[cohort$arm == 0])
estimate <- newer - standard

writeLines(toJSON(list(estimate = estimate), auto_unbox = TRUE, digits = 10), "/app/estimate.json")
