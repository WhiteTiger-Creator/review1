#!/bin/bash
set -euo pipefail

mkdir -p /app/output
export R_LIBS_USER=/app/environment/r_libs

Rscript -e '
source("/app/environment/rp3/loop_c.R")
m1 <- readRDS("/app/output/m1_tables.rds")
tags <- c("strict_mono", "relaxed_fast")
bundles <- c("w3", "w4", "k5")

# Epoch 1: refresh_flag = TRUE
for (b in bundles) {
  for (t in tags) {
    key <- paste0("bundle_", b, "_", t)
    wt <- m1$witness_tbls[[key]]
    split_cfg <- list(bundle = b, tag = t)
    out <- op_m3(wt, split_cfg, TRUE)
    m1$witness_tbls[[key]] <- out$emit_rows
  }
}

# Epoch 2: refresh_flag = FALSE (APPEND)
for (b in bundles) {
  for (t in tags) {
    key <- paste0("bundle_", b, "_", t)
    wt <- m1$witness_tbls[[key]]
    split_cfg <- list(bundle = b, tag = t)
    out <- op_m3(wt, split_cfg, FALSE)
    m1$witness_tbls[[key]] <- out$emit_rows
  }
}

saveRDS(m1, "/app/output/m1_tables.rds")
saveRDS(m1$witness_tbls, "/app/output/m2_witness.rds")
'
