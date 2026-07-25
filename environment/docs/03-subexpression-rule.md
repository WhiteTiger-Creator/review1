# Subexpression (capture group) rule

Once the overall match's start and end positions are fixed by the rule in
`02-overall-match-rule.md`, every group's reported span is determined by a
single deterministic walk over the pattern that must consume exactly that
fixed span, no more and no less, choosing among the possibilities as
follows:

- Alternation `X|Y|...`: try the branches in the order they are written.
  Use the first branch that still allows the rest of the pattern to consume
  exactly up to the fixed overall end. This is a preference for the
  earlier-listed branch, not for the longer branch -- a later branch is
  only used when every earlier branch makes it impossible to reach the
  required end exactly.
- Repetition (`*`, `+`, `?`, `{m}`, `{m,}`, `{m,n}`): the two detailed
  bullets below this one are the actual operational rule; "take as many
  repetitions as possible (greedy)" is only an informal summary of them,
  and must not be read as "search for whichever split of the fixed span
  across iterations yields the largest possible repetition *count*". The
  walk is a strict left-to-right, outer-to-inner attempt: each iteration,
  starting with the first, is tried with its own longest possible
  consumption first (recursing into whatever choices its own body makes,
  by the same rule), and only backtracks that iteration to a shorter
  consumption if no way of completing the rest of the pattern from the
  longer choice can reach the required end exactly. This means an earlier
  iteration is never deliberately shortened just so that a later iteration
  gets a chance to also fire -- the walk does not choose the split with
  the most repetitions, it chases the leftmost iteration's own greediest
  option first and only gives ground when that option is a dead end. See
  the second worked example in `05-worked-examples.md`, where this
  distinction changes the reported group span. When a group sits inside a
  repeated subexpression, its reported span is the span of the *last*
  repetition that occurred; if the repeated subexpression matched zero
  times, the group inside it is reported as unmatched.
- A repetition construct with an explicit finite upper bound (`{m,n}`,
  `{m}`, and `?`, which is `{0,1}`) treats every one of its `m` to `n`
  possible repetitions as a plain, ordered sequence of optional steps: each
  optional step beyond the mandatory first `m` is taken whenever it can
  match at all, even if it matches only the empty string.
- A repetition construct with no upper bound (`*`, `+`, and `{m,}`) takes
  its mandatory first `m` repetitions the same way, then continues taking
  further repetitions only as long as each one consumes at least one
  character. Once continuing would only add a repetition that matches the
  empty string, it stops there rather than taking that extra, contentless
  repetition -- except when zero non-empty repetitions have occurred yet at
  all, in which case exactly one contentless repetition is taken so the
  construct still reports a (zero-width) match instead of reporting no
  repetitions at all. This is what keeps `(a?)*` well-defined against a
  subject that contains no `a`: the loop still runs once, matching the
  empty string, rather than never running.
- A group that never participates in the winning walk (for example, the
  untaken branch of an alternation, or a quantified group that matched zero
  times) is reported as unmatched, distinctly from a group that matched an
  empty string.
- A group nested inside a repeated subexpression tracks its own span
  independently of its enclosing repeat. If the nested group participated
  in some earlier iteration of the enclosing repetition but the winning
  walk's *final* iteration of that repetition does not cause the nested
  group to participate again (for example, because the nested group is
  itself optional and has nothing left to match on that last iteration),
  the nested group keeps reporting the span from that earlier, most recent
  iteration in which it did participate -- it is not reset to unmatched
  just because the enclosing repetition's last iteration skipped it. A
  nested group is reported unmatched only if it never participates in any
  iteration of the winning walk at all. See the third worked example in
  `05-worked-examples.md`.

Three worked examples appear in `05-worked-examples.md`; read them alongside
this rule, since the interaction between alternation order and repetition
greediness is where a mismatched mental model (for example, assuming the
longer alternative always wins, assuming a repeated group reports its first
iteration, assuming repetition greediness maximizes iteration count rather
than each iteration's own consumption, or assuming a nested group resets to
unmatched whenever the enclosing repeat's last iteration does not touch it)
produces confidently wrong spans.
