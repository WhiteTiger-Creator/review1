#!/usr/bin/env bash
set -euo pipefail

ROOT=/app/environment
BOOK="${ROOT}/fixtures/exclbook/base.json"
SNAPS="${ROOT}/fixtures/snaps"
OUT="/app/output"
APPLY_UNIT_ENV=0
LANGPACK=""
SKIP_RECOVER=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --book)
      BOOK="$2"
      shift 2
      ;;
    --snaps)
      SNAPS="$2"
      shift 2
      ;;
    --out)
      OUT="$2"
      shift 2
      ;;
    --langpack)
      LANGPACK="$2"
      shift 2
      ;;
    --from-unit)
      APPLY_UNIT_ENV=1
      shift
      ;;
    --fresh)
      SKIP_RECOVER=1
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "${OUT}" /app/bin
make -C /app/environment PREFIX=/app install >/dev/null

touch -t 202001010101.00 "${SNAPS}/tree_a" "${SNAPS}/tree_a/metrics.json"
touch -t 202201010101.00 "${SNAPS}/tree_b" "${SNAPS}/tree_b/metrics.json"
touch -t 202401010101.00 "${SNAPS}/tree_c" "${SNAPS}/tree_c/metrics.json"

if [[ "${APPLY_UNIT_ENV}" -eq 1 ]]; then
  UNIT="${ROOT}/svcunit/metricd.service"
  while IFS= read -r line; do
    case "${line}" in
      Environment=*)
        export "${line#Environment=}"
        ;;
    esac
  done < "${UNIT}"
fi

if [[ -n "${LANGPACK}" ]]; then
  # shellcheck disable=SC1090
  source "${LANGPACK}"
fi

if [[ "${SKIP_RECOVER}" -eq 1 ]]; then
  rm -f "${OUT}/ship_journal.json" "${OUT}/canonical_export.sha256" "${OUT}/reconcile_trace.jsonl"
  rm -rf "${OUT}/stage"
fi

/app/bin/metricd --book "${BOOK}" --snaps "${SNAPS}" --out "${OUT}"
