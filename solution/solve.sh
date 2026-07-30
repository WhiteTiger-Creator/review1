#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app
patch -p1 < "$ROOT_DIR/oracle.patch"

chmod +x /app/environment/irc/cmd/irc
mkdir -p /app/output
