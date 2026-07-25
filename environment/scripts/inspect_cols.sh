#!/bin/bash
set -euo pipefail
Rscript -e 'm1<-readRDS("/app/output/m1_tables.rds"); cat(jsonlite::toJSON(colnames(m1$window_tbls$bundle_w3), auto_unbox=TRUE))'
