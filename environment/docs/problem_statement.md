# Principal square root by a determinantally scaled coupled iteration

Every case matrix `A` is real, symmetric, and positive definite of order `n`,
with `n` from 2 to 10. The principal square root `X` is the unique symmetric
positive-definite matrix with `X X = A`, and `Z` is its inverse, so `X Z = I`
and `Z Z = A^{-1}`.

## The pinned iteration

`X` and `Z` are defined here as the final iterates of the determinantally
scaled coupled (Denman-Beavers) iteration. Starting from

    Y_0 = A,
    W_0 = I,

at each step form the scale factor

    mu_k = | det(Y_k) det(W_k) | ^ ( -1 / (2 n) ),

and update

    Y_{k+1} = 0.5 * ( mu_k Y_k + (1/mu_k) W_k^{-1} ),
    W_{k+1} = 0.5 * ( mu_k W_k + (1/mu_k) Y_k^{-1} ),

running for exactly K = 24 steps (the constant MATSQRT_ITERS). Report:

- `X`, taken as `Y_K` (the iterate after all 24 steps);
- `Z`, taken as `W_K`;
- the scale trace `mu_0, mu_1, ..., mu_{K-1}`, one factor per step, in order.

Here `det` is the determinant, `|.|` its absolute value, and `M^{-1}` the
inverse of `M`. Every `mu_k` is a positive real number. The scale trace is part
of the graded answer, not diagnostic output. The graded matrices span a wide
range of eigenvalue magnitudes, and every reported factor and iterate must be
finite across that whole range.

## Input and output

The order `n` and the packed lower triangle of `A` come from the case file
described in `storage_format.md`. Write `X`, `Z`, and the scale trace to the
output path in the format of `output_format.md`. The acceptance conditions and
tolerances are in `result_contract.md`.
