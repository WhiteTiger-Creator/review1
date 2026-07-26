#!/usr/bin/env bash
set -euo pipefail

# Immutable, agent-visible inputs must be read-only. The evaluation project and
# the output directory stay writable so the agent can repair and rebuild.
find /data -type f -exec chmod a-w {} +
find /data -type d -exec chmod a-w {} +
find /app/docs -type f -exec chmod a-w {} +
find /app/docs -type d -exec chmod a-w {} +
find /app/worktrees -type f -exec chmod a-w {} +
find /app/worktrees -type d -exec chmod a-w {} +
chmod a-w /app/bin/lineage-audit
chmod a-w /app/VERIFIER.md

mkdir -p /output
chmod 0777 /output
