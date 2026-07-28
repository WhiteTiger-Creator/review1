#!/bin/bash
set -euo pipefail

mkdir -p /app/output
export R_LIBS_USER=/app/environment/r_libs

Rscript -e '
source("/app/environment/ws7/slice_a.R")
source("/app/environment/fc2/fit_b.R")
source("/app/environment/rp3/loop_c.R")

bundles <- list(
  w3 = list(
    annex = "/app/environment/fixtures/annex/bundle_w3.txt",
    judgments = "/app/environment/fixtures/judgments/bundle_w3.tsv"
  ),
  w4 = list(
    annex = "/app/environment/fixtures/annex/bundle_w4.txt",
    judgments = "/app/environment/fixtures/judgments/bundle_w4.tsv"
  ),
  k5 = list(
    annex = "/app/environment/fixtures/annex/bundle_k5.txt",
    judgments = "/app/environment/fixtures/judgments/bundle_k5.tsv"
  )
)

window_tbls <- list()
witness_tbls <- list()
prof_strict <- read_profile("/app/environment/profiles/strict_mono.toml")
prof_fast <- read_profile("/app/environment/profiles/relaxed_fast.toml")

for (key in names(bundles)) {
  spec <- bundles[[key]]
  jt <- read_judgments(spec$judgments)
  span_cfg <- list(window_tokens = prof_strict$window_tokens)
  staged <- op_m1(spec$annex, jt, span_cfg)
  window_tbls[[paste0("bundle_", key)]] <- staged$window_tbl
  w2 <- op_m2(staged$window_tbl, jt, prof_strict)
  witness_tbls[[paste0("bundle_", key, "_strict_mono")]] <- w2$witness_tbl
  w3 <- op_m2(staged$window_tbl, jt, prof_fast)
  witness_tbls[[paste0("bundle_", key, "_relaxed_fast")]] <- w3$witness_tbl
}

saveRDS(list(window_tbls = window_tbls, witness_tbls = witness_tbls), "/app/output/m1_tables.rds")
'
