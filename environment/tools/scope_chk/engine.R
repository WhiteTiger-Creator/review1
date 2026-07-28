source("/app/environment/lib/common_io.R")
source("/app/environment/rp3/loop_c.R")

bundle_code <- function(label) {
  if (label == "w3") 1L else if (label == "w4") 2L else 4L
}

tag_code <- function(label) {
  if (label == "strict_mono") 0L else 1L
}

fold_byte <- function(name) {
  if (name == "alpha") 1L else if (name == "beta") 2L else 3L
}

pack_f64_canonical <- function(x) {
  buf <- raw(8)
  writeBin(as.numeric(x), buf, endian = "big")
  buf
}

canonical_encode_replay_bytes <- function(bundle, tag, witness_tbl) {
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
      pack_f64_canonical(witness_tbl$residual[i]),
      pack_f64_canonical(witness_tbl$score[i])
    )
  }
  raw
}

chain_hex_of <- function(raw) {
  paste0(sprintf("%02x", as.integer(raw)), collapse = "")
}

check_monotonic <- function(witness_tbl, fold_order) {
  ord <- match(witness_tbl$fold, fold_order)
  scores <- witness_tbl$score[order(ord)]
  all(diff(scores) >= 1e-9)
}

check_residual_bounds <- function(witness_tbl, floor_v, eps_v) {
  all(abs(witness_tbl$residual) <= floor_v + eps_v + 1e-9)
}

run_bundle_tag <- function(bundle, tag) {
  prof_path <- sprintf("/app/environment/profiles/%s.toml", tag)
  prof <- read_profile(prof_path)
  m1 <- readRDS("/app/output/m1_tables.rds")
  key <- paste0("bundle_", bundle)
  window_tbl <- m1$window_tbls[[key]]
  witness_tbl <- m1$witness_tbls[[paste0(key, "_", tag)]]
  if (is.null(window_tbl) || is.null(witness_tbl)) {
    return(list(ok = FALSE, reason = "missing staged tables"))
  }
  
  cache_path <- sprintf("/app/output/.chain_cache_%s_%s.bin", bundle, tag)
  if (!file.exists(cache_path)) {
    return(list(ok = FALSE, reason = "missing cache ledger"))
  }
  raw <- readBin(cache_path, "raw", n = file.info(cache_path)$size)
  
  canon <- canonical_encode_replay_bytes(bundle, tag, witness_tbl)
  
  # The ledger must contain exactly two appended epochs
  expected_cache <- c(canon, canon)
  hex <- chain_hex_of(expected_cache)
  replay_ok <- identical(raw, expected_cache)
  
  mono <- check_monotonic(witness_tbl, prof$fold_order)
  bounds <- check_residual_bounds(witness_tbl, prof$residual_floor, prof$band_eps)
  list(
    ok = replay_ok && mono && bounds,
    chain_hex = hex,
    witness_tbl = witness_tbl,
    mono_band = prof$band_eps
  )
}
