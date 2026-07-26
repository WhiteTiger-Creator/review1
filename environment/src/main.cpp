#include <exception>
#include <iostream>

#include "mat_io.hpp"
#include "matsqrt.hpp"

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: matsqrt <case_file> <output_file>\n";
        return 2;
    }
    matsqrt::CaseData cd;
    try {
        cd = matsqrt::read_case_file(argv[1]);
    } catch (const std::exception& e) {
        std::cerr << "failed to read case file: " << e.what() << "\n";
        return 3;
    }
    matsqrt::MatSqrtResult r = matsqrt::matrix_sqrt(cd.A);
    if (!r.ok) {
        matsqrt::write_failure_output_file(argv[2], cd.n, "ERROR", r.message);
        std::cerr << "matrix_sqrt failed: " << r.message << "\n";
        return 4;
    }
    try {
        matsqrt::write_output_file(argv[2], r);
    } catch (const std::exception& e) {
        std::cerr << "failed to write output file: " << e.what() << "\n";
        return 3;
    }
    return 0;
}
