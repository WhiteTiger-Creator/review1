# Result contract

Every case matrix `A` is symmetric positive definite of order `n`. The program
reports two matrices `X` and `Z`, both `n` by `n`, and the scale trace
`mu_0, ..., mu_{K-1}` of the pinned iteration in `problem_statement.md`.

- `X` is symmetric and positive definite, and `X X = A`.
- `Z` is symmetric and positive definite, and `X Z = I`, where `I` is the
  identity. Equivalently `Z Z = A^{-1}`.
- Each `mu_k` is the determinantal scale factor of step `k` of the pinned
  iteration.

## Tolerances

The reported answer is accepted when, for the case matrix `A`,

- the relative residual `||X X - A||_F / ||A||_F` is at most `1e-7`,
- the largest entry magnitude of `X Z - I` is at most `1e-7`,
- `X` and `Z` are symmetric to within `1e-7` entrywise and are positive
  definite,
- each reported `mu_k` matches the scale factor of the pinned iteration to a
  relative tolerance of `1e-6`,

and every reported entry and scale factor is finite. `||.||_F` is the Frobenius
norm. Exact floating-point equality is never required.
