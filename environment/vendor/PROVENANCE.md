# Shared Fairy-variant environment bundle

`arena-vendor.tar.gz` contains the exact pinned Fairy-Stockfish 14 source
bundle and its documented behavior-neutral compiler patch, the generic
task-authored native arena source, the root-only bootstrap and health check,
and the offline pytest wheelhouse. The bundle does not contain a variant,
opening, difficulty, or result patch. Each task supplies its protected
`difficulty_knobs.conf`, including the exact built-in variant and opponent
search policy.

Every nested archive has an adjacent SHA-256 manifest. The Docker build checks
the outer bundle, checks each nested bundle, builds offline with one compiler
worker and `-O2`, and copies only the public client and README into `/app`.
