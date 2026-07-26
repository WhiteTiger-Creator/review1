#!/bin/bash
set -euo pipefail

cat > /app/environment/rp3/loop_c.R <<'EOF'
source("/app/environment/lib/common_io.R")

bundle_code <- function(label) {
  if (label == "w3") 1L else if (label == "w4") 2L else 4L
}

tag_code <- function(label) {
  if (label == "strict_mono") 0L else 1L
}

fold_byte <- function(name) {
  if (name == "alpha") 1L else if (name == "beta") 2L else 3L
}

pack_f64 <- function(x) {
  buf <- raw(8)
  writeBin(as.numeric(x), buf, endian = "big")
  buf
}

encode_replay_bytes <- function(bundle, tag, witness_tbl) {
  raw <- charToRaw("RLCR")
  n <- nrow(witness_tbl)
  cnt <- as.integer(n)
  raw <- c(raw, as.raw(cnt %/% 256), as.raw(cnt %% 256), as.raw(0), as.raw(0))
  for (i in seq_len(n)) {
    raw <- c(
      raw,
      as.raw(bundle_code(bundle)),
      as.raw(tag_code(tag)),
      as.raw(fold_byte(witness_tbl$fold[i])),
      pack_f64(witness_tbl$residual[i]),
      pack_f64(witness_tbl$score[i])
    )
  }
  raw
}

flush_chain_cache <- function(bundle, tag, refresh_flag) {
  cache_path <- sprintf("/app/output/.chain_cache_%s_%s.bin", bundle, tag)
  if (isTRUE(refresh_flag) && file.exists(cache_path)) {
    unlink(cache_path)
  }
  cache_path
}

op_m3 <- function(witness_tbl, split_cfg, refresh_flag) {
  bundle <- split_cfg$bundle
  tag <- split_cfg$tag
  cache_path <- flush_chain_cache(bundle, tag, refresh_flag)
  
  new_bytes <- encode_replay_bytes(bundle, tag, witness_tbl)
  
  if (file.exists(cache_path)) {
    existing_bytes <- readBin(cache_path, "raw", n = file.info(cache_path)$size)
    combined_bytes <- c(existing_bytes, new_bytes)
  } else {
    combined_bytes <- new_bytes
  }
  
  writeBin(combined_bytes, cache_path)
  list(emit_rows = witness_tbl, chain_bytes = combined_bytes)
}
EOF

rm -f /app/output/.chain_cache_*
