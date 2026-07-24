# Nested merge quarantine

Folding a policy bag into a root bag must refuse dangerous shared-object keys
such as `__proto__`, `constructor`, and `prototype` at every object depth,
including when those keys appear under otherwise ordinary nested objects.
Mask updates that set bits outside the active actor set for that slab must be
refused, leaving the prior mask in place. Safe keys must commute: folding a
patch and folding the same patch with object keys walked in reverse
lexicographic order must yield identical canonical digests (`knit_hex` equals
`pair_hex`). Nested objects must not alias across merge frames.

A privilege escalation is counted when a folded bag admits a mask bit outside
the active principals for that slab, or when a dangerous key lands on a shared
object during the fold. Across the closed algebra every row finishes with
`esc_hits` 0.
