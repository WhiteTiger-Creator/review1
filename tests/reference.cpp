#include "solver_core.cpp"

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    try {
        solve_file(argv[1], argv[2]);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
