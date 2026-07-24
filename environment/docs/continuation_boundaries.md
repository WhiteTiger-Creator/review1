# Continuation boundary examples

A boundary records the next numerical operation, not the last completed one. If physical layer two has eight substeps and the first three are complete, `next_layer` is two and `next_substep` is three. `completed_steps` is the number of substeps in earlier layers plus those three.

At the end of a physical layer, the boundary advances to the next layer with `next_substep` zero. At the end of the full Earth profile, `next_layer` is the configured layer count and `next_substep` is zero. Resumed propagation starts at the recorded boundary, so no substep is repeated or skipped.
