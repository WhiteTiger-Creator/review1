#!/bin/bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH}"
ROOT="/app/environment"
OUT="/app/output"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --out)
      OUT="$2"
      shift 2
      ;;
    -h|--help)
      echo "usage: recover_k4.sh [--root DIR] [--out DIR]"
      exit 0
      ;;
    *)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
  esac
done
mkdir -p "$OUT"
cd "$ROOT"
go build -o /tmp/k4bin ./cmd/k4
/tmp/k4bin recover --root "$ROOT" --out "$OUT"
