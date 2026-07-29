#!/usr/bin/env bash
set -euo pipefail

/app/bin/emsolve \
  --mesh /app/data/meshes/cavity_canonical.mesh \
  --modes 4 \
  --output /output/modes.json
