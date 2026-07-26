#include <algorithm>
#include <cmath>
#include <cstddef>

#include "matsqrt.hpp"

namespace matsqrt {

namespace {

Matrix inverse(const Matrix& A) {
    const std::size_t n = A.size();
    Matrix M(n, Vector(2 * n, 0.0));
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) M[i][j] = A[i][j];
        M[i][n + i] = 1.0;
    }
    for (std::size_t c = 0; c < n; ++c) {
        std::size_t p = c;
        for (std::size_t r = c + 1; r < n; ++r) {
            if (std::fabs(M[r][c]) > std::fabs(M[p][c])) p = r;
        }
        std::swap(M[c], M[p]);
        const double piv = M[c][c];
        for (std::size_t j = 0; j < 2 * n; ++j) M[c][j] /= piv;
        for (std::size_t r = 0; r < n; ++r) {
            if (r == c) continue;
            const double f = M[r][c];
            if (f == 0.0) continue;
            for (std::size_t j = 0; j < 2 * n; ++j) M[r][j] -= f * M[c][j];
        }
    }
    Matrix out(n, Vector(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) out[i][j] = M[i][n + j];
    }
    return out;
}

double log_abs_det(const Matrix& A) {
    const std::size_t n = A.size();
    Matrix M = A;
    double s = 0.0;
    for (std::size_t c = 0; c < n; ++c) {
        std::size_t p = c;
        for (std::size_t r = c + 1; r < n; ++r) {
            if (std::fabs(M[r][c]) > std::fabs(M[p][c])) p = r;
        }
        if (p != c) std::swap(M[c], M[p]);
        s += std::log(std::fabs(M[c][c]));
        for (std::size_t r = c + 1; r < n; ++r) {
            const double f = M[r][c] / M[c][c];
            for (std::size_t j = c; j < n; ++j) M[r][j] -= f * M[c][j];
        }
    }
    return s;
}

}

MatSqrtResult matrix_sqrt(const Matrix& A) {
    MatSqrtResult r;
    const std::size_t n = A.size();
    r.n = static_cast<int>(n);
    r.scale.reserve(MATSQRT_ITERS);

    Matrix Y = A;
    Matrix Z(n, Vector(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) Z[i][i] = 1.0;

    for (int it = 0; it < MATSQRT_ITERS; ++it) {
        const double ld = log_abs_det(Y) + log_abs_det(Z);
        const double g = std::exp(-ld / static_cast<double>(2 * n));
        const double gi = 1.0 / g;
        r.scale.push_back(g);

        const Matrix Yi = inverse(Y);
        const Matrix Zi = inverse(Z);
        Matrix Ynew(n, Vector(n, 0.0));
        Matrix Znew(n, Vector(n, 0.0));
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                Ynew[i][j] = 0.5 * (g * Y[i][j] + gi * Zi[i][j]);
                Znew[i][j] = 0.5 * (g * Z[i][j] + gi * Yi[i][j]);
            }
        }
        Y = Ynew;
        Z = Znew;
    }

    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < i; ++j) {
            const double sy = 0.5 * (Y[i][j] + Y[j][i]);
            Y[i][j] = Y[j][i] = sy;
            const double sz = 0.5 * (Z[i][j] + Z[j][i]);
            Z[i][j] = Z[j][i] = sz;
        }
    }

    r.X = Y;
    r.Z = Z;
    r.ok = true;
    return r;
}

}
