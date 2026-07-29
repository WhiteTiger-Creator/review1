#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
bash "$ROOT/scripts/build-gateway.sh"
REQUEST="${1:-/app/requests/release.json}"
OUTPUT="${2:-/output}"
mkdir -p "$OUTPUT"
"$ROOT/target/release/admission-gateway" evaluate --request "$REQUEST" --output "$OUTPUT"
