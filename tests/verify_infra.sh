#!/bin/bash
# Harness self-check (not scored). Fails fast if isolation or rebuild wiring breaks.
set -euo pipefail

export VERIFIER_BIN=/tmp/verifier-bin
export VERIFIER_SRC=/tmp/verifier-src
bash /tests/rebuild_task_binaries.sh

test -x "$VERIFIER_BIN/mirctl"
test -x "$VERIFIER_BIN/viewctl"
case "$(readlink -f "$VERIFIER_BIN/mirctl")" in
  /app/bin/*)
    echo "verifier binaries must not execute from /app/bin" >&2
    exit 1
    ;;
esac

for rel in cmd/mirctl/main.go cmd/viewctl/main.go go.mod; do
  path="$VERIFIER_SRC/$rel"
  test -f "$path"
  if runuser -u agent -- test -w "$path" 2>/dev/null; then
    echo "verifier source entrypoint must be write-locked for agent: $path" >&2
    exit 1
  fi
done

mkdir -p /logs/verifier
chown root:root /logs /logs/verifier 2>/dev/null || true
chmod 755 /logs 2>/dev/null || true
chmod 700 /logs/verifier 2>/dev/null || true
if runuser -u agent -- test -w /logs/verifier 2>/dev/null; then
  echo "agent must not write verifier reward path" >&2
  exit 1
fi
if runuser -u agent -- test -w /opt/verifier-venv/bin/python 2>/dev/null; then
  echo "agent must not write verifier python toolchain" >&2
  exit 1
fi
if runuser -u agent -- test -w /usr/local/go/bin/go 2>/dev/null; then
  echo "agent must not replace trusted go toolchain" >&2
  exit 1
fi

if chmod 700 /tests 2>/dev/null; then
  chmod 755 /tests/*.sh 2>/dev/null || true
  if runuser -u agent -- test -r /tests/test_outputs.py 2>/dev/null; then
    echo "agent must not read scored verifier tests" >&2
    exit 1
  fi
fi
