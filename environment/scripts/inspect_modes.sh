#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: inspect_modes.sh <modes.json>" >&2
  exit 2
fi

jq '{requested_modes, computed_modes, active_dofs, iterations, modes: [.modes[] | {index, eigenvalue, cluster_id, residuals}]}' "$1"
