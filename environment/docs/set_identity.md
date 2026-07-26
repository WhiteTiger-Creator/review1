Dependency-set identity digests

Edge digest

For gem name N and version V

edge_digest is the first 16 hex chars of sha256 over edge|N|V (lowercase)

Closure digest

Given an annex tag list T (edge digests, any first-walk order) and walk seed S

closure_digest is sha256 over S|0| joined with sorted(T) using |

Sorting is lexicographic on the hex strings. The middle field is the literal lane marker 0.

Permuting first-walk annex order must not change closure_digest for the same seed and gem dependency set. Changing the walk base must not change closure_digest either. Identity is over gem edges, not reloc addresses.

Do not feed activation order, overlay names, or reloc offsets into the closure reduction.

Mid-horizon resume must fold the same sorted edge set over completed-plus-pending gems. An encounter-order or activation-order body (for example from an on-path edge cache) is not an identity fold.
