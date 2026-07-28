#!/bin/bash
set -euo pipefail
bundle="${1:?bundle}"
tag="${2:?tag}"
Rscript -e "source('/app/environment/tools/scope_chk/engine.R'); res<-run_bundle_tag('${bundle}','${tag}'); cat(res\$chain_hex)"
