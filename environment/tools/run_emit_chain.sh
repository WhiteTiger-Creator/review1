#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/output
/app/environment/tools/rebuild_emit.sh
/app/environment/build/cmd/xbin/layer_emit --pair /app/environment/data/ref_h0.toml --journal /app/output/span.journal
/app/environment/build/cmd/yseal/yseal --journal /app/output/span.journal --report /app/output/span_transcript.json
