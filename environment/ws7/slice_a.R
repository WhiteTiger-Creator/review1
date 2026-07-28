source("/app/environment/lib/common_io.R")
source("/app/environment/rk4/legacy_e.R")

normalize_annex_tokens <- function(text) {
  toks <- strsplit(text, "\\s+")[[1]]
  toks[nchar(toks) > 0]
}

window_span <- function(tok_count, window_tokens) {
  max(1L, ceiling(tok_count / window_tokens))
}

op_m1 <- function(annex_paths, judgment_tbl, span_cfg) {
  window_tokens <- as.integer(span_cfg$window_tokens)
  rows <- list()
  carry_rows <- list()
  
  bundle_match <- regexpr("bundle_([a-z0-9]+)\\.txt", annex_paths[1])
  if (bundle_match > 0) {
    bundle <- substr(annex_paths[1], bundle_match + 7, bundle_match + attr(bundle_match, "match.length") - 5)
  } else {
    bundle <- "unknown"
  }

  for (path in annex_paths) {
    text <- paste(readLines(path, warn = FALSE), collapse = " ")
    toks <- normalize_annex_tokens(text)
    nwin <- window_span(length(toks), window_tokens)
    carry_running <- 0L
    for (w in seq_len(nwin)) {
      start <- (w - 1L) * window_tokens + 1L
      end <- min(w * window_tokens, length(toks))
      chunk <- toks[start:end]
      doc_ix <- ((w - 1L) %% nrow(judgment_tbl)) + 1L
      doc_id <- judgment_tbl$doc_id[doc_ix]
      
      base_rel <- judgment_tbl$relevance[doc_ix]
      rel <- resolve_relevance_policy(bundle, base_rel, doc_ix)
      
      carry_running <- carry_running + length(chunk)
      carry_val <- carry_running
      rows[[length(rows) + 1L]] <- data.frame(
        doc_id = doc_id,
        win_ix = w - 1L,
        tok_start = start - 1L,
        tok_count = length(chunk),
        carry_sum = carry_val,
        relevance = rel,
        stringsAsFactors = FALSE
      )
      carry_rows[[length(carry_rows) + 1L]] <- data.frame(
        doc_id = doc_id,
        win_ix = w - 1L,
        carry_sum = carry_val,
        stringsAsFactors = FALSE
      )
    }
  }
  list(
    window_tbl = do.call(rbind, rows),
    carry_tbl = do.call(rbind, carry_rows)
  )
}
