#!/bin/bash
set -euo pipefail
Rscript -e 'source("/app/environment/lib/common_io.R"); m1<-readRDS("/app/output/m1_tables.rds"); jt<-read_judgments("/app/environment/fixtures/judgments/bundle_w3.tsv"); wt<-m1$window_tbls$bundle_w3; cat(all(jt$doc_id %in% wt$doc_id))'
