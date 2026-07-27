#!/usr/bin/env bash
set -euo pipefail
# Terminal-Bench Canary: do not remove

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_ROOT="/app/environment"

# Restore the published object-archive link graph and pack configure:
# tooling helpers must not ride packing PUBLIC/INTERFACE edges, and the
# configure must not inject tooling macros into packing TUs.
patch -p1 -d "$ENV_ROOT" < "${ROOT_DIR}/patches/01-lib_wire.patch"
patch -p1 -d "$ENV_ROOT" < "${ROOT_DIR}/patches/02-bin_wire.patch"
patch -p1 -d "$ENV_ROOT" < "${ROOT_DIR}/patches/03-host.patch"

printf '3\n' >/app/environment/var/gen.stamp
printf 'gen=3 digest=cafebabecafebabe\n' >/app/environment/var/arc.fence
printf '00000000\n' >/app/environment/var/carry.side
bash /app/environment/tools/run_emit_chain.sh
