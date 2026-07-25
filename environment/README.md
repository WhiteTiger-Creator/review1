# matsqrt

A small C++ project that reads one symmetric matrix from a case file and writes
two matrices and a scale trace to an output path.

## Layout

- `include/matsqrt.hpp` — the public contract: the `MatSqrtResult` structure and
  the declaration of `matrix_sqrt`.
- `include/mat_io.hpp` — case-file reader and output writer. No changes needed.
- `src/main.cpp` — command-line driver. No changes needed.
- `src/matsqrt_impl.cpp` — the definition of `matrix_sqrt`; a starter stub is
  provided and must be replaced.
- `data/` — example case files.
- `docs/` — input format, output format, the pinned iteration, and the result
  contract.

## Build and run

    ./build.sh
    ./build/matsqrt data/case_spd_n5_c6.txt /tmp/out.txt

`build.sh` configures and builds with CMake into `build/`. Any `.cpp` file you
add under `src/` besides `main.cpp` is compiled and linked into the `matsqrt`
executable.
