# Shared Fairy-variant solution bundle

`solution-vendor.tar.gz` contains the exact pinned Fairy-Stockfish 14 source,
license, documented behavior-neutral compiler patch, and task-authored generic
oracle source. `solve.sh` authenticates every layer, builds offline using one
compiler worker and `-O2`, and selects the task's variant and disclosed oracle
node budget through environment variables.

The oracle plays exclusively through `/app/arena`, submits one move at a time,
stops after terminal play, and exits successfully only after a genuine White
win with zero postgame participant requests.
