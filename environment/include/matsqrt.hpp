#ifndef MATSQRT_HPP
#define MATSQRT_HPP

#include <string>
#include <vector>

namespace matsqrt {

using Vector = std::vector<double>;
using Matrix = std::vector<std::vector<double>>;

constexpr int MATSQRT_ITERS = 24;

struct MatSqrtResult {
    int n = 0;
    Matrix X;
    Matrix Z;
    Vector scale;
    bool ok = false;
    std::string message = "none";
};

MatSqrtResult matrix_sqrt(const Matrix& A);

}

#endif
