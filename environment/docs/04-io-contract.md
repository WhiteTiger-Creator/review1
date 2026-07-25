# Build and I/O contract

Build with:

    cd /app && go build -o /app/posixmatch ./src

The binary is invoked as:

    posixmatch <pattern> <subject>

Both arguments are plain command-line arguments (the subject is never read
from stdin or a file). The program prints to stdout and exits 0 in every
case below except a pattern parse error.

- If the pattern is not a well-formed ERE under `01-grammar.md` -- which is
  the sole authority on well-formedness, including its explicit list of
  patterns that must be rejected (unbalanced parentheses, a reversed
  bracket range, a trailing backslash, a stacked duplication symbol) and
  its separate list of patterns that look irregular but are in fact
  well-formed -- print exactly one line, `PARSE_ERROR`, and exit with
  status 1. Ill-formed patterns are a deliberate, graded part of the input
  set, not an edge case that can be assumed away.
- If the pattern is well-formed but does not match the subject at all
  (no starting position produces any match), print exactly one line,
  `NOMATCH`, and exit 0.
- If the pattern matches, print one line `MATCH <start> <end>` giving the
  overall match's start offset and end offset (0-based, end exclusive, byte
  offsets into the subject), followed by one line per capturing group, in
  group-number order 1..N: `GROUP <n> <start> <end>` if that group
  participated in the match, or `GROUP <n> NOMATCH` if it did not. Exit 0.

Nothing else is written to stdout. The implementation must be written from
scratch: no standard-library or third-party regular-expression package or
function (for example Go's `regexp` package, or calling out to a C library's
`regcomp`/`regexec` via cgo) may be used anywhere in the submitted source.
Only the Go standard library outside of `regexp` is available, and the
build must succeed offline.
