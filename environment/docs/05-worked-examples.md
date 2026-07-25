# Worked examples

## Alternation order beats alternation length

Pattern `(a|ab)(c|bcd)(d*)` against subject `"abcd"`.

The overall match is the whole string, `"abcd"` (offsets 0 to 4) -- it is
both leftmost and longest available.

Group 1 is `(a|ab)`. Try `a` first (it is listed first). If group 1 takes
`a`, the remaining subject to account for is `"bcd"` starting at offset 1.
Group 2 is `(c|bcd)`; try `c` first, but the character at offset 1 is `b`,
not `c`, so that branch fails outright; fall back to `bcd`, which matches
`"bcd"` exactly (offsets 1 to 4). Group 3, `(d*)`, then has nothing left to
consume and matches zero repetitions at offset 4 (an empty match, not
unmatched, since `*` always succeeds).

Because taking `a` for group 1 already lets the rest of the pattern reach
the required end exactly, `ab` (the second, longer alternative) is never
tried for group 1.

Result: `MATCH 0 4`, `GROUP 1 0 1`, `GROUP 2 1 4`, `GROUP 3 4 4`.

A matcher that assumes the *longer* alternative always wins would instead
try `ab` for group 1, then `c` for group 2, then `d` for group 3, also
reaching offset 4 -- a different, wrong split of the same correct overall
span.

## A repeated group reports its last iteration

Pattern `(ab)*` against subject `"ababab"`.

The overall match is the whole string (offsets 0 to 6). The group `(ab)`
repeats three times: `"ab"` at 0-2, `"ab"` at 2-4, `"ab"` at 4-6. The group
is reported as it stood after the *last* repetition, offsets 4 to 6, not
the first repetition's offsets 0 to 2.

Result: `MATCH 0 6`, `GROUP 1 4 6`.

## Repetition greediness maximizes each iteration's own consumption, not the iteration count

Pattern `((.)+){0,2}` against subject `"ba"`.

The overall match is the whole string (offsets 0 to 2) -- both leftmost and
longest. Group 1 is `(.)+` repeated `{0,2}` times; group 2 is the `.` inside
it.

Consider the first of the two possible repetitions of group 1. Its own body,
`(.)+`, is itself greedy: tried on its own at offset 0 with nothing yet
requiring it to stop early, it consumes as many characters as it can, which
is both remaining characters, `"ba"` (offsets 0 to 2). Because that already
lets the rest of the pattern (there is nothing left) reach the required end
exactly, this first repetition of group 1 is accepted with that full span,
and the construct's second, optional repetition of group 1 is never even
attempted -- there is nothing left in the subject for it to consume. Group 1
is therefore reported using this single, first repetition's span, `0 2`.
Inside that repetition, `(.)+`'s own last-iteration rule applies to group 2:
its final `.` consumed the second character, offsets 1 to 2.

Result: `MATCH 0 2`, `GROUP 1 0 2`, `GROUP 2 1 2`.

A matcher that instead searches for whichever split maximizes the *number*
of repetitions of group 1 would give the first repetition only the first
character (`"b"`, offsets 0 to 1) specifically so the second, optional
repetition could also fire (consuming `"a"`, offsets 1 to 2) -- reaching the
same overall end by a different route, and reporting group 1 as `1 2`
instead of the correct `0 2`. This is a real fork (it is what some other
POSIX-compliant matchers, such as glibc's regexec, actually do), but it is
not the rule this task specifies: the first repetition's own greediness is
resolved before the enclosing construct ever considers whether a further
repetition would also be possible, not the other way around.

## A nested group can report a span from an earlier iteration than its enclosing group

Pattern `(a(b)?)*` against subject `"aba"`.

The overall match is the whole string (offsets 0 to 3). Group 1, `(a(b)?)`,
repeats twice: first over `"ab"` (offsets 0 to 2, where the nested group 2
matches `"b"` at offsets 1 to 2), then over `"a"` (offsets 2 to 3, where the
nested group 2's `(b)?` has nothing left to match at offset 3 and takes its
empty option instead).

Group 1 is reported using its last repetition's span, offsets 2 to 3, per
the usual rule. Group 2, however, did not participate in that last
repetition at all (the `(b)?` inside it matched nothing, not even an empty
string, because there is nothing new for it to record) -- so group 2
retains the span it was given during the *earlier* repetition where it last
actually took part: offsets 1 to 2.

Result: `MATCH 0 3`, `GROUP 1 2 3`, `GROUP 2 1 2`.

A matcher that resets every nested group to unmatched whenever its
enclosing repetition's final iteration does not touch it would wrongly
report `GROUP 2 NOMATCH` here, instead of correctly carrying forward the
span from group 2's own last participating iteration.
