read_enrollment <- function(data_dir = Sys.getenv("CAUSAL_DATA_DIR", "/app/data")) {
  read.csv(file.path(data_dir, "enrollment.csv"), stringsAsFactors = FALSE)
}

read_followup <- function(data_dir = Sys.getenv("CAUSAL_DATA_DIR", "/app/data")) {
  read.csv(file.path(data_dir, "followup.csv"), stringsAsFactors = FALSE)
}

read_site_calendar <- function(data_dir = Sys.getenv("CAUSAL_DATA_DIR", "/app/data")) {
  read.csv(file.path(data_dir, "site_calendar.csv"), stringsAsFactors = FALSE)
}
