# posixmatch

A conformance checker for POSIX 1003.1 extended regular expression (ERE)
matching: for any pattern and subject it reports the standard-defined
leftmost-longest overall match and each capturing group's span. Exact matching
semantics matter for input validation and access-control rules, where a matcher
that diverges from the standard causes validation bypasses. See `docs/` for the
full grammar, the leftmost-longest overall-match rule, the subexpression
disambiguation rule, and the I/O contract. Sample pattern/subject pairs with
their standard-defined output are under `data/` (one file per case).

Build:

    cd /app && go build -o /app/posixmatch ./src

Run:

    /app/posixmatch '(a|ab)(c|bcd)(d*)' 'abcd'
