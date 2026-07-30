#!/usr/bin/env bash
# Re-exec under bash when invoked as `sh solve.sh` (pipefail is bash-only).
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT_DIR}"

mkdir -p /app/environment/ax /app/environment/by /app/environment/cz /app/environment/ez /app/environment/qx

bash "${ROOT_DIR}/apply/bank.sh"
bash "${ROOT_DIR}/apply/loom.sh"
bash "${ROOT_DIR}/apply/step.sh"
bash "${ROOT_DIR}/apply/tick.sh"
bash "${ROOT_DIR}/apply/emit.sh"

chmod +x /app/environment/exec/tacts
/app/environment/exec/tacts build
/app/environment/exec/tacts play --all
