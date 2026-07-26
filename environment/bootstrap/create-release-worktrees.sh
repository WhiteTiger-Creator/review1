#!/usr/bin/env bash
set -euo pipefail

# Materialize the two release-candidate worktrees from the deterministic seed.
# Each worktree is an independent Git repository with fixed commit metadata so
# its state is reproducible across image builds.

SEED="/app/release-repo-seed"
export GIT_AUTHOR_NAME="release-bot"
export GIT_AUTHOR_EMAIL="release-bot@acme.test"
export GIT_COMMITTER_NAME="release-bot"
export GIT_COMMITTER_EMAIL="release-bot@acme.test"
export GIT_AUTHOR_DATE="2024-07-01T00:00:00+0000"
export GIT_COMMITTER_DATE="2024-07-01T00:00:00+0000"

for name in rc-blue rc-green; do
    dest="/app/worktrees/${name}"
    mkdir -p "${dest}"
    cp -a "${SEED}/${name}/." "${dest}/"
    git -C "${dest}" init -q
    git -C "${dest}" add -A
    git -C "${dest}" commit -q -m "${name} release candidate"
done

# The seed is no longer needed at runtime.
rm -rf "${SEED}"
