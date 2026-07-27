#!/bin/bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
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
      echo "usage: drive_k4.sh [--root DIR] [--out DIR]  # fit-score evaluate"
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
/tmp/k4bin fit-score --root "$ROOT" --out "$OUT"
