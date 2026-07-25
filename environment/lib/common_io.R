read_profile <- function(path) {
  lines <- readLines(path, warn = FALSE)
  kv <- list()
  for (ln in lines) {
    if (!nzchar(ln) || startsWith(ln, "#")) next
    if (!grepl("=", ln, fixed = TRUE)) next
    parts <- strsplit(ln, "=", fixed = TRUE)[[1]]
    key <- trimws(parts[1])
    val <- trimws(paste(parts[-1], collapse = "="))
    if (startsWith(val, "[") && endsWith(val, "]")) {
      inner <- substring(val, 2L, nchar(val) - 1L)
      items <- strsplit(inner, ",")[[1]]
      kv[[key]] <- trimws(gsub("\"", "", items))
    } else if (grepl("^[0-9.]+$", val)) {
      kv[[key]] <- as.numeric(val)
    } else {
      kv[[key]] <- gsub("\"", "", val)
    }
  }
  kv
}

read_judgments <- function(path) {
  df <- read.delim(path, stringsAsFactors = FALSE)
  df
}
