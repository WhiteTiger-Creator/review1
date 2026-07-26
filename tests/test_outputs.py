"""Behavioral verifier for denman-beavers-matrix-square-root.

Pure Python only (no numpy or any numerical library).  The task pins a concrete
computation: the determinantally scaled coupled (Denman-Beavers) iteration for
the principal square root of a symmetric positive-definite A,

    Y_0 = A,  W_0 = I,
    mu_k = |det(Y_k) det(W_k)|^(-1/(2n)),
    Y_{k+1} = 0.5 (mu_k Y_k + mu_k^{-1} W_k^{-1}),
    W_{k+1} = 0.5 (mu_k W_k + mu_k^{-1} Y_k^{-1}),

run for K = 24 steps.  The graded answer is X = Y_K, Z = W_K and the scale trace
mu_0 .. mu_{K-1}.

The verifier builds the candidate binary from a frozen, root-owned copy of the
fixed sources (/opt/fixed) plus the agent's src/matsqrt_impl.cpp, with a
hardcoded g++ command, so only src/matsqrt_impl.cpp can influence behavior.  For
each case it fixes a real positive spectrum, builds A = Q D Q^T with an integer
orthogonal Q (so A is exactly symmetric positive definite and its square root is
known by construction), and grades:

  (a) well-formedness: finite numbers and correct shapes;
  (b) symmetry and positive definiteness of X and Z;
  (c) ||X X - A||_F / ||A||_F within tolerance;
  (d) max entry magnitude of X Z - I within tolerance;
  (e) mu_0 against the certified anchor (prod|lambda|)^{-1/(2n)} computed in the
      log domain from the exact spectrum;
  (f) the full scale trace against an independent LU-based recomputation whose
      inverse and log-determinant use a different elimination than the oracle.

The graded matrices span a wide range of eigenvalue magnitudes: |det A| routinely
lies far outside the range of a double, so the scale factors must be formed
without ever materializing that determinant.  A handful of small example case
files are shipped under environment/data/ for development; none of them is used
for grading, and no reference X, Z, or trace is shipped.
"""

from __future__ import annotations

import math
import pathlib
import random
import subprocess
from fractions import Fraction as F

import pytest

ENV = pathlib.Path("/app/environment")
AGENT_IMPL = ENV / "src" / "matsqrt_impl.cpp"
FIXED = pathlib.Path("/opt/fixed")
BIN = pathlib.Path("/tmp/verify_matsqrt")
CASE_FILE = pathlib.Path("/tmp/verify_case.txt")
OUT_FILE = pathlib.Path("/tmp/verify_out.txt")

K = 24  # pinned iteration count (MATSQRT_ITERS)
TOL_X2A = 1e-7
TOL_XZ = 1e-7
TOL_SYM = 1e-7
SCALE_TOL = 1e-6

# --------------------------------------------------------------------------
# pure-python dense linear algebra (row-major list-of-lists)
# --------------------------------------------------------------------------


def zeros(n):
    return [[0.0] * n for _ in range(n)]


def ident(n):
    m = zeros(n)
    for i in range(n):
        m[i][i] = 1.0
    return m


def matmul(A, B, n):
    C = zeros(n)
    for i in range(n):
        Ai, Ci = A[i], C[i]
        for k in range(n):
            a = Ai[k]
            if a == 0.0:
                continue
            Bk = B[k]
            for j in range(n):
                Ci[j] += a * Bk[j]
    return C


def fro(A, n):
    s = 0.0
    for i in range(n):
        for j in range(n):
            v = A[i][j]
            s += v * v
    return math.inf if not math.isfinite(s) else math.sqrt(s)


def rel_resid(XX, A, n):
    num = 0.0
    den = 0.0
    for i in range(n):
        for j in range(n):
            d = XX[i][j] - A[i][j]
            num += d * d
            den += A[i][j] * A[i][j]
    if not math.isfinite(num) or not math.isfinite(den):
        return math.inf
    return math.sqrt(num) / max(math.sqrt(den), 1e-300)


def max_off_identity(M, n):
    return max(
        abs(M[i][j] - (1.0 if i == j else 0.0)) for i in range(n) for j in range(n)
    )


def max_asym(M, n):
    return max(
        (abs(M[i][j] - M[j][i]) for i in range(n) for j in range(n)), default=0.0
    )


def is_pd(M, n):
    L = zeros(n)
    for i in range(n):
        for j in range(i + 1):
            s = M[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if not (s > 0.0):
                    return False
                L[i][j] = math.sqrt(s)
            else:
                if L[j][j] == 0.0:
                    return False
                L[i][j] = s / L[j][j]
    return True


# ----- independent LU-based inverse and log|det| (verifier reference) ------


def lu_decompose(A, n):
    M = [row[:] for row in A]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if M[p][c] == 0.0:
            return None
        if p != c:
            M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            M[r][c] /= M[c][c]
            f = M[r][c]
            if f != 0.0:
                for j in range(c + 1, n):
                    M[r][j] -= f * M[c][j]
    return M


def gj_inverse(A, n):
    """Gauss-Jordan inverse with partial pivoting (distinct code path)."""
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if M[p][c] == 0.0:
            return None
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        inv = 1.0 / piv
        M[c] = [v * inv for v in M[c]]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c]
            if f != 0.0:
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def lu_logabsdet(A, n):
    M = lu_decompose(A, n)
    if M is None:
        return None
    return sum(math.log(abs(M[i][i])) for i in range(n))


def ref_trace(A, n):
    """Independent recomputation of the pinned iteration's scale trace and
    final iterates, using LU log-determinants and Gauss-Jordan inverses."""
    Y = [row[:] for row in A]
    W = ident(n)
    gs = []
    for _k in range(K):
        ldy = lu_logabsdet(Y, n)
        ldw = lu_logabsdet(W, n)
        if ldy is None or ldw is None:
            return None
        g = math.exp(-(ldy + ldw) / (2 * n))
        Yi = gj_inverse(Y, n)
        Wi = gj_inverse(W, n)
        if Yi is None or Wi is None:
            return None
        gs.append(g)
        ig = 1.0 / g
        Yn = [[0.5 * (g * Y[i][j] + ig * Wi[i][j]) for j in range(n)] for i in range(n)]
        Wn = [[0.5 * (g * W[i][j] + ig * Yi[i][j]) for j in range(n)] for i in range(n)]
        if not all(math.isfinite(v) for row in Yn for v in row):
            return None
        Y, W = Yn, Wn
    return gs, Y, W


# --------------------------------------------------------------------------
# construction of known SPD triples: A = Q D Q^T, D positive
# --------------------------------------------------------------------------


def eident(n):
    return [[F(i == j) for j in range(n)] for i in range(n)]


def emm(A, B, n):
    C = [[F(0)] * n for _ in range(n)]
    for i in range(n):
        for k in range(n):
            a = A[i][k]
            if a:
                for j in range(n):
                    C[i][j] += a * B[k][j]
    return C


def householder_int(rng, n):
    """Exact rational Householder reflector R = I - 2 v v^T / (v.v), orthogonal."""
    while True:
        v = [rng.randint(-2, 2) for _ in range(n)]
        if any(x != 0 for x in v):
            break
    vv = sum(x * x for x in v)
    return [[F(i == j) - F(2 * v[i] * v[j], vv) for j in range(n)] for i in range(n)]


def dyadic(rng, e):
    """Odd 5-bit mantissa times 2**(e-5): exactly representable when in range."""
    return F(rng.randrange(16, 32)) * F(2) ** (e - 5)


def representable(A, n):
    for i in range(n):
        for j in range(n):
            x = float(A[i][j])
            if not math.isfinite(x) or F(x) != A[i][j]:
                return False
    return True


def logabs_frac(fr):
    return math.log(abs(fr.numerator)) - math.log(fr.denominator)


def build_spd(rng, n, base_e, spread):
    """Return (A_float, spectrum_logmods) for a symmetric positive-definite A."""
    for _ in range(400):
        eigs = [
            dyadic(rng, base_e + (rng.randrange(-spread, spread + 1) if spread else 0))
            for _ in range(n)
        ]
        Q = eident(n)
        for _ in range(rng.choice([1, 2])):
            Q = emm(Q, householder_int(rng, n), n)
        D = [[F(0)] * n for _ in range(n)]
        for i in range(n):
            D[i][i] = eigs[i]
        QT = [[Q[j][i] for j in range(n)] for i in range(n)]
        A = emm(emm(Q, D, n), QT, n)
        if representable(A, n):
            Af = [[float(A[i][j]) for j in range(n)] for i in range(n)]
            return Af, [logabs_frac(e) for e in eigs]
    raise RuntimeError(f"SPD not representable for n={n}, base_e={base_e}")


def build_battery():
    rng = random.Random(20260725)
    cases = []
    idx = 0

    def add(tag, n, base_e, spread):
        nonlocal idx
        A, logmods = build_spd(rng, n, base_e, spread)
        cases.append((idx, tag, n, A, logmods))
        idx += 1

    # Wide-magnitude families: |det A| ~ 2^(+-1100), far outside double range, so
    # forming the determinant as a product of pivots overflows or underflows.
    # These start at n = 3: at n = 2 the Frobenius norm of A would itself
    # overflow when |det A| does (they share the same scale).
    for n in range(3, 11):
        e = max(6, math.ceil(1100 / n))
        add("big", n, e, 3)
        add("small", n, -e, 3)
    # Modest-magnitude families with increasing condition number (the product
    # determinant survives here, so these force the correct determinant SCALING
    # rather than only the overflow handling).
    for n in range(2, 11):
        add("unit", n, 0, 4)
        add("s8", n, 0, 8)
        add("cond", n, 0, 12)
        add("s16", n, 0, 16)
        add("illcond", n, 0, 20)
    # A few larger wide cases.
    for n in (7, 9, 10):
        e = max(6, math.ceil(1400 / n))
        add("bigger", n, e, 4)
    return cases


BATTERY = build_battery()

# --------------------------------------------------------------------------
# build / run / io helpers
# --------------------------------------------------------------------------


def _build():
    """Compile from the frozen fixed sources plus the agent's matsqrt_impl.cpp
    with a hardcoded command; never trust the agent's CMake or other files."""
    assert FIXED.is_dir(), f"{FIXED} missing; image not built as expected"
    assert AGENT_IMPL.is_file(), f"{AGENT_IMPL} missing"
    cmd = [
        "g++",
        "-O2",
        "-std=c++17",
        "-Wall",
        f"-I{FIXED}",
        str(FIXED / "main.cpp"),
        str(AGENT_IMPL),
        "-o",
        str(BIN),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert r.returncode == 0, f"compile failed:\n{r.stderr}"


def _write_case(A, n):
    parts = [str(n)]
    for i in range(n):
        parts.append(" ".join(format(A[i][j], ".17g") for j in range(i + 1)))
    CASE_FILE.write_text("\n".join(parts) + "\n")


def _run():
    if OUT_FILE.exists():
        OUT_FILE.unlink()
    r = subprocess.run(
        [str(BIN), str(CASE_FILE), str(OUT_FILE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, f"matsqrt exited {r.returncode}\nstderr:\n{r.stderr}"
    assert OUT_FILE.exists(), "no output file was written"


def _parse_output(n):
    lines = OUT_FILE.read_text().splitlines()
    pos = 0

    def nxt():
        nonlocal pos
        assert pos < len(lines), "output ended unexpectedly"
        s = lines[pos]
        pos += 1
        return s

    assert nxt().startswith("n="), "expected n= line"
    assert nxt().startswith("status=OK"), "expected status=OK"
    assert nxt().startswith("message="), "expected message= line"

    def read_matrix(label):
        assert nxt() == label, f"expected {label} section"
        return [[float(v) for v in nxt().split()] for _ in range(n)]

    X = read_matrix("X")
    Z = read_matrix("Z")
    assert nxt() == "SCALE", "expected SCALE section"
    mu = [float(nxt()) for _ in range(K)]
    return X, Z, mu


@pytest.fixture(scope="module", autouse=True)
def _built():
    _build()


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------


def test_binary_builds_successfully():
    assert BIN.exists() and BIN.is_file()


@pytest.mark.parametrize(
    "case", BATTERY, ids=[f"{c[0]:02d}-{c[1]}-n{c[2]}" for c in BATTERY]
)
def test_case(case):
    """Recover X, Z and the pinned scale trace, satisfying every condition."""
    _idx, _tag, n, A, logmods = case
    _write_case(A, n)
    _run()
    X, Z, mu = _parse_output(n)

    assert len(X) == n and all(len(r) == n for r in X), "X wrong shape"
    assert len(Z) == n and all(len(r) == n for r in Z), "Z wrong shape"
    assert all(math.isfinite(v) for r in X for v in r), "X has non-finite values"
    assert all(math.isfinite(v) for r in Z for v in r), "Z has non-finite values"
    assert all(math.isfinite(x) and x > 0.0 for x in mu), (
        "scale factors must be finite positive"
    )

    assert max_asym(X, n) <= TOL_SYM, f"X not symmetric ({max_asym(X, n):.2e})"
    assert max_asym(Z, n) <= TOL_SYM, f"Z not symmetric ({max_asym(Z, n):.2e})"
    assert is_pd(X, n), "X is not positive definite"
    assert is_pd(Z, n), "Z is not positive definite"

    rx = rel_resid(matmul(X, X, n), A, n)
    assert rx <= TOL_X2A, f"||X X - A||/||A|| = {rx:.3e} exceeds {TOL_X2A:.1e}"

    rxz = max_off_identity(matmul(X, Z, n), n)
    assert rxz <= TOL_XZ, f"max|X Z - I| = {rxz:.3e} exceeds {TOL_XZ:.1e}"

    # (e) mu_0 against the certified anchor from the exact spectrum (log domain)
    g0_true = math.exp(-sum(logmods) / (2 * n))
    assert abs(mu[0] - g0_true) <= SCALE_TOL * g0_true, (
        f"mu_0={mu[0]:.6e} differs from certified {g0_true:.6e}"
    )

    # (f) full scale trace against the independent LU-based recomputation
    ref = ref_trace(A, n)
    assert ref is not None, "reference iteration failed"
    gref, _Yr, _Wr = ref
    for k in range(K):
        assert abs(mu[k] - gref[k]) <= SCALE_TOL * abs(gref[k]) + 1e-300, (
            f"mu_{k}={mu[k]:.6e} differs from reference {gref[k]:.6e}"
        )


def test_case_count_meets_minimum():
    assert len({c[0] for c in BATTERY}) == len(BATTERY), "duplicate case id"
    assert len(BATTERY) >= 60, f"only {len(BATTERY)} graded cases, expected >= 60"


def test_example_case_files_present():
    for name in ("case_spd_n5_c6", "case_toy"):
        assert (ENV / "data" / f"{name}.txt").exists(), f"missing example {name}.txt"


def test_interface_contract_unaltered():
    header = (FIXED / "matsqrt.hpp").read_text()
    assert "MatSqrtResult matrix_sqrt(const Matrix& A);" in header, "signature altered"
    for field in ("Matrix X", "Matrix Z", "Vector scale", "bool ok"):
        assert field in header, f"expected field {field!r} missing"


# --------------------------------------------------------------------------
# adversarial negatives: each shortcut is recomputed here and shown to fail,
# proving the discriminating power of the scale-trace grade is real.
# --------------------------------------------------------------------------


def _prod_absdet(A, n):
    M = lu_decompose(A, n)
    if M is None:
        return 0.0
    d = 1.0
    for i in range(n):
        d *= M[i][i]
    return abs(d)


def _trace_with(A, n, scaling):
    """Recompute the coupled iteration using a chosen scaling rule.  Returns the
    scale trace, or None if it produces a non-finite value (a rejection)."""
    Y = [row[:] for row in A]
    W = ident(n)
    gs = []
    for _k in range(K):
        Yi = gj_inverse(Y, n)
        Wi = gj_inverse(W, n)
        if Yi is None or Wi is None:
            return None
        if scaling == "prodet":
            d = _prod_absdet(Y, n) * _prod_absdet(W, n)
            if d == 0.0 or not math.isfinite(d):
                return None
            g = d ** (-1.0 / (2 * n))
        elif scaling == "frob":
            ny = fro(Y, n)
            nwi = fro(Wi, n)
            if not math.isfinite(ny) or not math.isfinite(nwi) or ny == 0.0:
                return None
            g = math.sqrt(nwi / ny)
        else:  # "none": no scaling
            g = 1.0
        if not math.isfinite(g) or g == 0.0:
            return None
        ig = 1.0 / g
        gs.append(g)
        Yn = [[0.5 * (g * Y[i][j] + ig * Wi[i][j]) for j in range(n)] for i in range(n)]
        Wn = [[0.5 * (g * W[i][j] + ig * Yi[i][j]) for j in range(n)] for i in range(n)]
        if not all(math.isfinite(v) for row in Yn for v in row):
            return None
        Y, W = Yn, Wn
    return gs


def _reference_mu0(logmods, n):
    return math.exp(-sum(logmods) / (2 * n))


def test_naive_product_determinant_is_rejected():
    """Forming |det| as a product of pivots overflows or underflows on the wide
    cases, so the mu it produces is non-finite; every wide case must break."""
    wide = 0
    broke = 0
    for _idx, tag, n, A, _lm in BATTERY:
        if tag in ("big", "small", "bigger"):
            wide += 1
            if _trace_with(A, n, "prodet") is None:
                broke += 1
    assert wide > 0
    assert broke == wide, (
        f"naive product determinant must break on every wide case, {broke}/{wide}"
    )


def test_frobenius_scaling_trace_is_rejected():
    """A full but Frobenius-scaled iteration produces a valid square root yet a
    different scale trace, so it must fail the scale grade on every case."""
    failed = 0
    for _idx, _tag, n, A, logmods in BATTERY:
        g0 = _reference_mu0(logmods, n)
        ft = _trace_with(A, n, "frob")
        if ft is None or abs(ft[0] - g0) > SCALE_TOL * g0:
            failed += 1
    assert failed == len(BATTERY), (
        f"Frobenius scaling must fail the trace grade everywhere, {failed}/{len(BATTERY)}"
    )


def test_unscaled_iteration_is_rejected():
    """The unscaled coupled iteration (mu_k = 1) yields the wrong trace on every
    case, and does not even converge on the wide ones."""
    failed = 0
    for _idx, _tag, n, A, logmods in BATTERY:
        g0 = _reference_mu0(logmods, n)
        ut = _trace_with(A, n, "none")
        if ut is None or abs(ut[0] - g0) > SCALE_TOL * g0:
            failed += 1
    assert failed == len(BATTERY), (
        f"unscaled iteration must fail the trace grade everywhere, {failed}/{len(BATTERY)}"
    )


def test_return_A_is_rejected():
    """Returning X = A (and Z = I) misses the X X = A residual by orders of
    magnitude on every conditioned case."""
    bad = 0
    for _idx, _tag, n, A, _lm in BATTERY:
        rx = rel_resid(matmul(A, A, n), A, n)
        if not math.isfinite(rx) or rx > TOL_X2A:
            bad += 1
    assert bad == len(BATTERY), "returning A must miss the residual on every case"


def test_no_forbidden_libraries():
    """No external linear-algebra routines are referenced in the agent source."""
    forbidden = [
        "dgesv",
        "dpotrf",
        "dsyev",
        "dgeev",
        "dgesvd",
        "cblas_",
        "gsl_linalg",
        "gsl_matrix",
        "Eigen::",
        "LAPACKE_",
        "armadillo",
        "#include <mkl",
    ]
    text = AGENT_IMPL.read_text()
    for sym in forbidden:
        assert sym not in text, f"forbidden symbol '{sym}' in src/matsqrt_impl.cpp"
