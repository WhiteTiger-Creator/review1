# Threshold policy

Threshold rules count distinct authorized principals with usable attestations for the exact
predicate and artifact. The canonical satisfying set is the lexicographically smallest sorted
principal list among all valid satisfying sets.

Every required predicate must have at least one usable authorized attestation even when no
additional threshold rule is attached to that predicate.
