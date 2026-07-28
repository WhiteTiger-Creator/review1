#!/bin/bash
set -euo pipefail
bundle="${1:?bundle}"
tag="${2:?tag}"
Rscript -e "source('/app/environment/tools/scope_chk/engine.R'); wt<-run_bundle_tag('${bundle}','${tag}')\$witness_tbl; prof<-read_profile('/app/environment/profiles/${tag}.toml'); cat(check_monotonic(wt, prof\$fold_order))"
