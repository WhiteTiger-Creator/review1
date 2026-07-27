#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-/var/lib/mint}"
if [ -d /opt/task-fixtures/pristine/fixtures/base-store ]; then
  rm -rf "$TARGET"
  mkdir -p "$TARGET"
  cp -a /opt/task-fixtures/pristine/fixtures/base-store/. "$TARGET/"
else
  rm -rf "$TARGET"
  mkdir -p "$TARGET/blobs/sha256" "$TARGET/snapshots" "$TARGET/manifests"
fi
