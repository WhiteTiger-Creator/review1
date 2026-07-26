source("/app/environment/lib/common_io.R")

op_m1 <- function(annex_paths, judgment_tbl, span_cfg) {
  window_tokens <- as.integer(span_cfg$window_tokens)
  rows <- list()
  carry_rows <- list()
  for (path in annex_paths) {
    text <- paste(readLines(path, warn = FALSE), collapse = " ")
    toks <- strsplit(text, "\\s+")[[1]]
    toks <- toks[nchar(toks) > 0]
    nwin <- max(1L, ceiling(length(toks) / window_tokens))
    for (w in seq_len(nwin)) {
      start <- (w - 1L) * window_tokens + 1L
      end <- min(w * window_tokens, length(toks))
      chunk <- toks[start:end]
      doc_ix <- ((w - 1L) %% nrow(judgment_tbl)) + 1L
      doc_id <- judgment_tbl$doc_id[doc_ix]
      rel <- judgment_tbl$relevance[doc_ix]
      carry_val <- length(chunk)
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
