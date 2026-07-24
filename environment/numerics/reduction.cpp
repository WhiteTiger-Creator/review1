#include "reduction.hpp"

#include <mpi.h>

double num_mass_observe(const std::vector<double>& owned, double dx, int n_global, int rank,
                        int nproc) {
    (void)n_global;
    (void)nproc;
    double local = 0.0;
    for (double v : owned) {
        local += v;
    }
    local *= dx;
    double global = 0.0;
    MPI_Allreduce(&local, &global, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    (void)rank;
    return global;
}
