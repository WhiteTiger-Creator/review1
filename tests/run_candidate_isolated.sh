#!/usr/bin/env bash
# Restricted candidate runner for the cmake-reconciler verifier.
#
# Usage: run_candidate_isolated.sh <binary> -- [args...]
#
# Remaps --data-dir into a private input jail and --report-out into a candidate-owned
# output jail, then copies produced outputs back to the host paths. Executes as uid
# 9001 when setpriv/runuser is available, with a cleared environment.
set -euo pipefail

if [[ "${1:-}" == "" || "${2:-}" != "--" ]]; then
  echo "usage: run_candidate_isolated.sh <binary> -- [args...]" >&2
  exit 2
fi

CANDIDATE_BIN="$1"
shift 2

if [[ ! -x "$CANDIDATE_BIN" ]]; then
  echo "candidate binary is missing or not executable: $CANDIDATE_BIN" >&2
  exit 2
fi

CANDIDATE_UID="${CANDIDATE_UID:-9001}"
CANDIDATE_GID="${CANDIDATE_GID:-9001}"
# Must match the Dockerfile-created system user (uid/gid 9001).
CANDIDATE_USER="${CANDIDATE_USER:-cmakecandidate}"
WORK_ROOT="$(mktemp -d /var/tmp/cmake-candidate-work.XXXXXX 2>/dev/null || mktemp -d /tmp/cmake-candidate-work.XXXXXX)"
OUTPUT_DIR="$WORK_ROOT/output"
INPUT_DIR="$WORK_ROOT/input"
WRITABLE_DIR="$WORK_ROOT/writable"
mkdir -p "$OUTPUT_DIR" "$INPUT_DIR" "$WRITABLE_DIR"
chmod 755 "$WORK_ROOT" "$INPUT_DIR" "$OUTPUT_DIR" "$WRITABLE_DIR"

declare -a HOST_OUTPUT_MAP=()

cleanup() {
  local entry host jail
  for entry in "${HOST_OUTPUT_MAP[@]:-}"; do
    [[ -z "$entry" ]] && continue
    host="${entry%%=*}"
    jail="${entry#*=}"
    if [[ -f "$jail" ]]; then
      mkdir -p "$(dirname "$host")"
      cp -f "$jail" "$host" 2>/dev/null || true
    else
      rm -f "$host" 2>/dev/null || true
    fi
    rm -f "${host}.tmp"
    if [[ -f "${jail}.tmp" ]]; then
      rm -f "${jail}.tmp"
    fi
  done
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

ensure_candidate_user() {
  if id -u "$CANDIDATE_USER" >/dev/null 2>&1; then
    return 0
  fi
  if ! getent group "$CANDIDATE_GID" >/dev/null 2>&1; then
    groupadd --system --gid "$CANDIDATE_GID" cmakecandidate 2>/dev/null || true
  fi
  if command -v useradd >/dev/null 2>&1; then
    useradd --system --no-create-home --uid "$CANDIDATE_UID" --gid "$CANDIDATE_GID" --shell /usr/sbin/nologin "$CANDIDATE_USER" 2>/dev/null || \
      useradd --system --no-create-home --uid "$CANDIDATE_UID" --shell /usr/sbin/nologin "$CANDIDATE_USER" 2>/dev/null || true
  fi
}

apply_deny_lockdown() {
  local deny
  for deny in /tests /solution /logs /logs/verifier; do
    if [[ -e "$deny" ]]; then
      chmod o-rwx "$deny" 2>/dev/null || true
      find "$deny" -type d -exec chmod o-rwx {} + 2>/dev/null || true
      find "$deny" -type f -exec chmod o-rwx {} + 2>/dev/null || true
    fi
  done
}

declare -a JAIL_ARGS=()
DATA_COUNT=0
prev=""
for arg in "$@"; do
  if [[ "$prev" == "--data-dir" ]]; then
    if [[ -d "$arg" ]]; then
      DATA_COUNT=$((DATA_COUNT + 1))
      data_jail="$INPUT_DIR/data-$DATA_COUNT"
      mkdir -p "$data_jail"
      cp -a "$arg"/. "$data_jail"/
      chmod -R a+rX "$data_jail"
      JAIL_ARGS+=("$data_jail")
    else
      JAIL_ARGS+=("$arg")
    fi
    prev=""
    continue
  fi
  if [[ "$prev" == "--report-out" ]]; then
    base="$(basename "$arg")"
    jail_path="$OUTPUT_DIR/$base"
    HOST_OUTPUT_MAP+=("$arg=$jail_path")
    mkdir -p "$(dirname "$arg")"
    if [[ -f "${arg}.tmp" ]]; then
      cp -f "${arg}.tmp" "${jail_path}.tmp"
    fi
    rm -f "$arg" "${arg}.tmp"
    JAIL_ARGS+=("$jail_path")
    prev=""
    continue
  fi
  if [[ "$arg" == "--data-dir" || "$arg" == "--report-out" ]]; then
    JAIL_ARGS+=("$arg")
    prev="$arg"
    continue
  fi
  JAIL_ARGS+=("$arg")
  prev=""
done

ensure_candidate_user
chown -R "$CANDIDATE_UID:$CANDIDATE_GID" "$OUTPUT_DIR" "$WRITABLE_DIR" 2>/dev/null || true
chmod -R a+rX "$INPUT_DIR" 2>/dev/null || true
chmod a+rx "$CANDIDATE_BIN" 2>/dev/null || true

# Deny-path lockdown: stamp avoids repeating the expensive find on every call,
# but always re-apply when the stamp is missing (fresh container / remount).
LOCKDOWN_STAMP="/tmp/.cmake-verifier-lockdown-done"
if [[ ! -f "$LOCKDOWN_STAMP" ]]; then
  apply_deny_lockdown
  touch "$LOCKDOWN_STAMP" 2>/dev/null || true
fi

run_as_candidate() {
  if command -v setpriv >/dev/null 2>&1; then
    setpriv \
      --reuid="$CANDIDATE_UID" \
      --regid="$CANDIDATE_GID" \
      --clear-groups \
      --nnp \
      --inh-caps=-all \
      --ambient-caps=-all \
      --bounding-set=-all \
      -- "$@"
    return $?
  fi
  if command -v runuser >/dev/null 2>&1 && id -u "$CANDIDATE_USER" >/dev/null 2>&1; then
    runuser -u "$CANDIDATE_USER" -- "$@"
    return $?
  fi
  # No privilege-drop tool available; refuse rather than run as root.
  echo "isolation failure: setpriv/runuser unavailable; refusing to run as root" >&2
  return 126
}

if [[ "${CANDIDATE_ISOLATION_SELFCHECK:-}" == "1" ]]; then
  fail=0
  # Remounts can restore world-readable modes; re-lock before probing.
  apply_deny_lockdown
  uid="$(run_as_candidate id -u 2>/dev/null || echo 0)"
  if [[ "$uid" == "0" ]]; then
    echo "isolation self-check failed: candidate UID is 0" >&2
    fail=1
  fi
  for p in \
    /tests \
    /tests/test_outputs.py \
    /tests/reference/engine.py \
    /solution \
    /solution/oracle_src \
    /logs/verifier/reward.txt
  do
    if run_as_candidate test -r "$p" 2>/dev/null; then
      echo "isolation self-check failed: prohibited path is readable: $p" >&2
      fail=1
    fi
  done
  env_dump="$(run_as_candidate env -i HOME="$WRITABLE_DIR" PATH="/usr/local/bin:/usr/bin:/bin" PWD="$WRITABLE_DIR" env 2>/dev/null || true)"
  if printf '%s\n' "$env_dump" | grep -Eq '(^| )PYTHONPATH=/tests($| )'; then
    echo "isolation self-check failed: candidate environment exposes PYTHONPATH=/tests" >&2
    fail=1
  fi
  if [[ "$fail" -ne 0 ]]; then
    exit 1
  fi
  echo "isolation self-check passed"
  exit 0
fi

cd "$WRITABLE_DIR"
set +e
run_as_candidate env -i \
  HOME="$WRITABLE_DIR" \
  PATH="/usr/local/bin:/usr/bin:/bin" \
  PWD="$WRITABLE_DIR" \
  "$CANDIDATE_BIN" "${JAIL_ARGS[@]}"
rc=$?
set -e
exit "$rc"
