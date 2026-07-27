#!/bin/bash
set -euo pipefail
export PATH="/usr/local/go/bin:/usr/local/bin:${PATH}"
exec /app/bin/nfs-acld /app/config/exports.json
