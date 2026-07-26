#ifndef MATSQRT_MAT_IO_HPP
#define MATSQRT_MAT_IO_HPP

#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "matsqrt.hpp"

namespace matsqrt {

struct CaseData {
    int n = 0;
    Matrix A;
};

inline CaseData read_case_file(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("cannot open case file: " + path);
    }
    std::vector<double> tokens;
    std::string line;
    while (std::getline(in, line)) {
        std::size_t first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        if (line[first] == '#') continue;
        std::istringstream iss(line);
        double v;
        while (iss >> v) tokens.push_back(v);
    }
    if (tokens.empty()) {
        throw std::runtime_error("case file has no data: " + path);
    }
    const int n = static_cast<int>(tokens[0]);
    if (n <= 0) {
        throw std::runtime_error("case file declares non-positive n: " + path);
    }
    const std::size_t lower = static_cast<std::size_t>(n) * (static_cast<std::size_t>(n) + 1) / 2;
    const std::size_t expected = 1 + lower;
    if (tokens.size() != expected) {
        throw std::runtime_error("case file token count mismatch in " + path +
                                 ": expected " + std::to_string(expected) +
                                 ", got " + std::to_string(tokens.size()));
    }
    CaseData cd;
    cd.n = n;
    cd.A.assign(static_cast<std::size_t>(n), Vector(static_cast<std::size_t>(n), 0.0));
    std::size_t idx = 1;
    for (int i = 0; i < n; ++i) {
        for (int j = 0; j <= i; ++j) {
            const double v = tokens[idx++];
            cd.A[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] = v;
            cd.A[static_cast<std::size_t>(j)][static_cast<std::size_t>(i)] = v;
        }
    }
    return cd;
}

namespace detail {

inline void write_matrix(std::ofstream& out, const Matrix& M) {
    for (const auto& row : M) {
        for (std::size_t j = 0; j < row.size(); ++j) {
            if (j > 0) out << ' ';
            out << std::setprecision(17) << row[j];
        }
        out << '\n';
    }
}

}

inline void write_output_file(const std::string& path, const MatSqrtResult& r) {
    std::ofstream out(path);
    if (!out) {
        throw std::runtime_error("cannot open output file for writing: " + path);
    }
    out << "n=" << r.n << '\n';
    out << "status=OK\n";
    out << "message=" << (r.message.empty() ? "none" : r.message) << '\n';
    out << "X\n";
    detail::write_matrix(out, r.X);
    out << "Z\n";
    detail::write_matrix(out, r.Z);
    out << "SCALE\n";
    for (double s : r.scale) {
        out << std::setprecision(17) << s << '\n';
    }
}

inline void write_failure_output_file(const std::string& path, int n,
                                      const std::string& status,
                                      const std::string& message) {
    std::ofstream out(path);
    if (!out) {
        throw std::runtime_error("cannot open output file for writing: " + path);
    }
    std::string clean = message.empty() ? "none" : message;
    for (char& c : clean) {
        if (c == '\n' || c == '\r') c = ' ';
    }
    out << "n=" << n << '\n';
    out << "status=" << status << '\n';
    out << "message=" << clean << '\n';
}

}

#endif
