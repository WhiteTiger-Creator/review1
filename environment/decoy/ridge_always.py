"""Off-path ridge helper — not used by latchml."""
def fit_ridge(X, y, lam=1.0):
    return [lam] + [0.0] * (len(X[0]) - 1 if X else 0)
