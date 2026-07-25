# Overall match rule: leftmost, then longest

Given a pattern and a subject, the overall match is determined in two steps,
applied in this order:

1. Leftmost: consider candidate starting positions in the subject in
   increasing order, 0, 1, 2, .... The overall match starts at the first
   position for which the pattern can match *some* substring beginning
   there. Positions before that one are never used, even if a match
   starting later would be longer.
2. Longest: once the starting position is fixed, among every substring
   starting there that the pattern can match, the overall match is the
   longest one.

This is different from a backtracking engine's usual behavior (Perl,
Python's `re`, most hand-written recursive matchers), which stops at the
first successful parse it finds while scanning alternation branches and
repetition counts left to right, and therefore usually returns a *shorter*
match than the longest one actually available. A matcher that returns the
first successful parse instead of searching for the provably longest one
will disagree with the required output on any subject where a longer match
exists further down an alternation or through more repetitions.

Example: against the pattern `a|ab` and the subject `"ab"`, the overall
match is `"ab"` (positions 0 to 2), not `"a"` (positions 0 to 1), because
`ab` is longer and starts at the same (leftmost) position. A backtracking
engine that tries the `a` branch first and stops there would wrongly report
`"a"`.

Only after the overall span is fixed does the question of which
subexpression matched which part of it arise; that is a separate rule,
described in `03-subexpression-rule.md`.
