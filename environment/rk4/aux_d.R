# ingest helper for headline counts only
op_aux <- function(a, b) {
  counts <- vapply(a, function(p) length(strsplit(readLines(p), "\\s+")[[1]]), integer(1))
  list(headline = sum(counts))
}
