#!/usr/bin/env Rscript
source("/app/environment/tools/scope_chk/engine.R")

args <- commandArgs(trailingOnly = TRUE)
suite <- "all"
tags <- c("strict_mono", "relaxed_fast")
out_path <- "/app/output/residual_scope.json"

i <- 1L
while (i <= length(args)) {
  if (args[i] == "--suite") {
    suite <- args[i + 1L]
    i <- i + 2L
  } else if (args[i] == "--tags") {
    tags <- strsplit(args[i + 1L], ",", fixed = TRUE)[[1]]
    i <- i + 2L
  } else if (args[i] == "--bundle-out") {
    out_path <- args[i + 1L]
    i <- i + 2L
  } else {
    i <- i + 1L
  }
}

bundles <- if (suite == "all") c("w3", "w4", "k5") else strsplit(suite, ",", fixed = TRUE)[[1]]
report <- list(bundles = list())
status <- 0L

for (b in bundles) {
  report$bundles[[b]] <- list()
  for (t in tags) {
    res <- run_bundle_tag(b, t)
    block <- list(
      residual_rows = res$witness_tbl,
      chain_hex = res$chain_hex,
      mono_band = res$mono_band
    )
    report$bundles[[b]][[t]] <- block
    if (!isTRUE(res$ok)) {
      status <- 1L
    }
  }
}

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
jsonlite::write_json(report, out_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)
quit(save = "no", status = status)
