#include <cstddef>

#include "matsqrt.hpp"

namespace matsqrt {

// Starter stub: returns X = A, Z = I and an all-zero scale trace. This
// compiles and runs but does not satisfy the result contract; replace the body
// with a correct implementation.
MatSqrtResult matrix_sqrt(const Matrix& A) {
    MatSqrtResult r;
    const std::size_t n = A.size();
    r.n = static_cast<int>(n);
    r.X = A;
    r.Z.assign(n, Vector(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) r.Z[i][i] = 1.0;
    r.scale.assign(static_cast<std::size_t>(MATSQRT_ITERS), 0.0);
    r.ok = true;
    return r;
}

}
