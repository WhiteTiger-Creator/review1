# Kyoto Shogi opponent policy

The opponent and oracle are separate builds of the exact same pinned,
unmodified Fairy-Stockfish 14 source with the same documented behavior-neutral
compiler identifier patch. Both use the built-in `kyotoshogi` rules, its pinned
opening, classical evaluation, one thread, and full skill. There is no
role-specific source, hidden opening book, tablebase, network service, rule
patch, or result override.

The protected environment policy searches exactly 20,000 nodes for each Black
reply with a 16 MiB hash and `MultiPV=2`, then deterministically chooses the
second-ranked line. The oracle uses `MultiPV=1`, a 64 MiB hash, and exactly
100,000 nodes per White move. These disclosed search-policy settings are the
only intentional strength difference. The live referee independently checks
every proposed Black move against the pinned rules before atomically committing
White's move and Black's reply.
