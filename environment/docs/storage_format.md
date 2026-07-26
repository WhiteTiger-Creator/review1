# Case file format

Each `case_*.txt` file describes one symmetric matrix `A` of order `n`.

Tokens are whitespace separated and may span multiple lines. Blank lines and
lines whose first non-space character is `#` are ignored.

The token stream is:

1. `n`, the order of the matrix, a positive integer.
2. The packed lower triangle of `A`, row by row: for row `i` from `0` to `n-1`,
   the entries `A[i][0], A[i][1], ..., A[i][i]`. That is `n(n+1)/2` values.

The matrix is symmetric, so `A[j][i] = A[i][j]`; only the lower triangle is
stored. There is no right-hand side.

Example (`n = 2`, with `A = [[1, 2], [2, 1]]`):

    2
    1
    2 1
