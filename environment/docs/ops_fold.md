# Certificate fold

Independent-replay folds operate on the concatenated window list and the
concatenated delta list across transcript rows in lane order. Before hashing,
sort only the window list by ascending `t0`, then `t1`, then `tx`. Leave the
delta list in the original concatenation order; do not reorder deltas to follow
the sorted windows.

Accumulate privilege with `/app/environment/corpus/ribx.json` `grant_mask`: for
each index `i` in `0 .. max(wins, dels) - 1`, take delta `d = dels[i]` as an
unsigned 32-bit integer (missing deltas are 0). If `(d & ~grant_mask)` is
nonzero, count one escalation and skip that delta; otherwise add
`(d & grant_mask)` into an unsigned 32-bit accumulator. Map the accumulator into
a published ribx slot `[lo, hi)`: when the accumulator lands in a slot, `band` is
that slot's `mid`; when no slot matches, `band` falls back to the last slot mid
if any slots exist, otherwise `acc & 0xff`.

`digest` is SHA-256 of the UTF-8 bytes of canonical compact JSON with this shape:

```
{"acc":<u32>,"band":<int>,"dels":[u32,...],"esc":<int>,"wins":[[t0,t1,tx],...]}
```

Key order follows sorted-key canonicalization. Per-lane observations use the same
fold on that row's windows and deltas alone. `replay_digest` must equal `digest`
from a second independent fold. `in_band` is true when `band` falls inside a
published ribx slot.

Dashboard shadow files under `/app/output/.nubx_shadow` must never override the
independent fold result.
