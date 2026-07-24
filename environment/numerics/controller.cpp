#include "controller.hpp"

#include "../core/advance.hpp"

#include <mpi.h>

#include <algorithm>
#include <cmath>
#include <vector>

CtrlState num_ctrl_defaults(const ProfKnobs& prof, double kappa, double dx) {
    CtrlState c{};
    c.last_dt = adv_pick_dt(kappa, dx, prof.dt0, prof.cfl);
    c.n_reject = 0;
    c.n_accept = 0;
    c.accum = 1.0;
    return c;
}

namespace {

void halo_exchange(std::vector<double>& owned, std::vector<double>& glo, std::vector<double>& ghi,
                   int rank, int nproc) {
    MPI_Status st;
    if (rank > 0) {
        MPI_Sendrecv(owned.data(), 1, MPI_DOUBLE, rank - 1, 11, glo.data(), 1, MPI_DOUBLE, rank - 1,
                     12, MPI_COMM_WORLD, &st);
    } else {
        glo[0] = 0.0;
    }
    if (rank < nproc - 1) {
        MPI_Sendrecv(owned.data() + static_cast<int>(owned.size()) - 1, 1, MPI_DOUBLE, rank + 1, 12,
                     ghi.data(), 1, MPI_DOUBLE, rank + 1, 11, MPI_COMM_WORLD, &st);
    } else {
        ghi[0] = 0.0;
    }
}

}  // namespace

int num_ctrl_advance(std::vector<double>& owned, std::vector<double>& glo, std::vector<double>& ghi,
                     CtrlState& ctrl, HistRec& hist, const ProfKnobs& prof, double kappa, double dx,
                     int lo, int hi, int n_global, int rank, int nproc) {
    halo_exchange(owned, glo, ghi, rank, nproc);
    const double dt = adv_pick_dt(kappa, dx, prof.dt0, prof.cfl);
    adv_ftcs_step(owned, glo, ghi, kappa, dx, dt, lo, hi, n_global);
    ctrl.last_dt = dt;
    ctrl.n_accept += 1;
    if (rank == 0) {
        hist.dt_seq.push_back(dt);
        hist.step += 1;
    }
    return 0;
}

CtrlState num_ctrl_restore(const GlobRec& glob, const ProfKnobs& prof, double kappa, double dx) {
    (void)glob;
    return num_ctrl_defaults(prof, kappa, dx);
}
