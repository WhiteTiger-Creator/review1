# Supported ERE grammar

This is the exact pattern grammar the matcher must implement: literals,
`.`, concatenation, alternation `|`, grouping `(...)`, the postfix
duplication symbols listed below, bracket expressions `[...]`, the anchors
`^` and `$`, and backslash-escaping. No construct outside this list -- no
backreference, no POSIX named class like `[[:alpha:]]`, no lookaround, no
non-greedy modifier -- ever appears in any graded pattern.

This file is also the sole authority on which patterns built from that list
are well-formed. The graded pattern set deliberately includes patterns that
combine these same characters in ways that are *not* well-formed (an
unbalanced parenthesis, a reversed bracket range, and so on); every such
case is enumerated at the end of this file, alongside a companion list of
patterns that look irregular but are in fact well-formed. `04-io-contract.md`
describes how an ill-formed pattern must be reported (`PARSE_ERROR`). A
matcher validated only against well-formed input will not have exercised
this required behavior.

- Ordinary literal characters match themselves.
- `.` matches any single character in the subject. Subjects never contain a
  newline, so no character is excluded.
- Concatenation: writing two subexpressions next to each other matches one
  followed by the other.
- Alternation `|`: `X|Y` matches anything `X` matches or anything `Y`
  matches. Alternation may have more than two branches (`X|Y|Z`) and the
  order the branches are written in is significant (see
  `03-subexpression-rule.md`).
- Grouping `(...)`: parentheses group a subexpression and also capture it.
  Groups are numbered 1, 2, 3, ... in the order their opening parenthesis
  appears in the pattern, left to right, independent of nesting depth.
- Postfix duplication symbols apply to the single atom immediately before
  them (a literal, `.`, a bracket expression, or a `(...)` group):
  - `*` zero or more
  - `+` one or more
  - `?` zero or one
  - `{m}` exactly m
  - `{m,}` m or more
  - `{m,n}` between m and n, inclusive
  A duplication symbol never appears directly after another duplication
  symbol on the same atom (`a**`, `a*{2,3}`, `a+?`, ...); such a stacked
  construct is rejected as PARSE_ERROR, per the reject list below.
  Repeating a repetition is always written with an explicit group,
  e.g. `(a*)*`.
- Bracket expressions `[...]`: match one character drawn from the listed
  set. `[^...]` (caret as the first character inside the brackets) matches
  one character *not* in the listed set. A member can be a single character
  or an inclusive range `a-z`. A `]` listed as the very first member of the
  set (`[]a]` or `[^]a]`) is an ordinary member, not the closing bracket. A
  `-` listed as the first or last member of the set is an ordinary member,
  not a range operator.
- Anchors `^` and `$` are special in every position they occur in the
  pattern, not only at the very start or end -- this is a real difference
  from BRE (and from most backtracking engines' mental model), where the
  same characters are only sometimes special. `^` matches a zero-width
  position only at the true start of the subject; `$` matches a zero-width
  position only at the true end of the subject. A pattern such as `a^b` can
  never match anything, because the `^` in the middle of the pattern
  demands a position that a mid-string `^` can never reach.
- A backslash `\` makes the following character an ordinary literal, even if
  it would otherwise be one of the characters above. This bullet applies
  outside bracket expressions only -- see the bracket-expression bullet
  above and the irregular-but-well-formed list below for the exception.
- There are no backreferences. ERE (unlike BRE) never has them.

Patterns and subjects are restricted to printable, non-newline ASCII bytes.

## Patterns that look irregular but are well-formed

- An empty branch is well-formed and matches the empty string at that
  point, not a parse error. `()` is a group whose body matches zero
  characters every time it is used. `(a|)` and `(|a)` are alternations
  with one non-empty and one empty branch; the empty branch matches zero
  characters, and the alternation-order rule in `03-subexpression-rule.md`
  decides which branch is used when both could complete the match.
- An opening `{` that is not immediately followed by at least one digit
  (before its optional comma) does not start an interval at all, even if a
  digit and closing `}` appear later. Every interval form this grammar
  supports (`{m}`, `{m,}`, `{m,n}`) requires an explicit `m` right after
  the `{`. So in `a{,2}` the `{` has no digit immediately after it: it,
  the `,`, the `2`, and the `}` are each read as an ordinary literal
  character in turn. The whole pattern `a{,2}` is five literal characters,
  not an interval.
- Backslash has no special meaning inside a bracket expression `[...]`.
  There, a `\` is an ordinary member of the set like any other character,
  and whatever character immediately follows it is a separate, second
  ordinary member -- never an escaped literal. For example `[\)]` is a
  two-member set containing the literal characters `\` and `)`.

## Patterns that must be rejected as PARSE_ERROR

- A `)` with no preceding unclosed `(` (for example `a)`, or a pattern
  that is just `)`), or a `(` that is never closed by a matching `)`
  before the pattern ends (for example `(a`).
- A bracket range whose start collates after its end, such as `[z-a]`
  (`z` collates after `a`): rejected outright, independent of whether the
  matcher would ever need to test the range against a subject character.
- A trailing, unescaped backslash at the very end of the pattern (`a\`, or
  a pattern that is just `\`), since there is no following character left
  for it to escape.
- A duplication symbol stacked directly on another duplication symbol on
  the same atom, per the "never appears directly after another duplication
  symbol" rule already stated above under postfix duplication symbols.
