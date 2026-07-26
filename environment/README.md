# environment (maintainer notes)

Offline machine-learning ensemble model-risk evaluation image.

* Digest-pinned Temurin JDK base for the offline evaluator under `/app/environment`.
* `bootstrap/create-release-worktrees.sh` materializes the two candidate model
  lineages from `app-seed/release-repo-seed` at image-build time with fixed Git
  metadata for reproducibility.
* Evaluator dependencies are warmed during the build so runtime rebuilds stay
  offline.
* `bootstrap/lock-input-permissions.sh` makes `/data`, `/app/docs`, and
  `/app/worktrees` read-only while keeping `/app/environment` and `/output`
  writable for the agent.
* Neither `tests/` nor `solution/` is copied into the image.
