#include "partition.hpp"

#include "../core/advance.hpp"

#include <algorithm>
#include <cmath>

DistRec restart_partition(const GlobRec& glob, int nproc, int rank) {
    DistRec dist{};
    dist.rank = rank;
    dist.nproc = nproc;
    dist.step = glob.step;
    dist.dx = adv_dx(glob.ncell);

    const int chunk = static_cast<int>(std::ceil(static_cast<double>(glob.ncell) / nproc));
    int lo = rank * chunk;
    int loc_n = std::min(chunk, std::max(0, glob.ncell - lo));
    int hi = lo + loc_n - 1;
    if (loc_n <= 0) {
        lo = 0;
        hi = -1;
        loc_n = 0;
    }

    dist.owned.resize(static_cast<size_t>(loc_n));
    dist.gids.resize(static_cast<size_t>(loc_n));
    dist.ghost_lo = {0.0};
    dist.ghost_hi = {0.0};
    for (int i = 0; i < loc_n; ++i) {
        const int g = lo + i;
        dist.owned[static_cast<size_t>(i)] = glob.vals[static_cast<size_t>(g)];
        dist.gids[static_cast<size_t>(i)] = g;
    }
    if (loc_n > 0) {
        dist.ghost_lo[0] = (lo == 0) ? 0.0 : glob.vals[static_cast<size_t>(lo - 1)];
        dist.ghost_hi[0] =
            (hi == glob.ncell - 1) ? 0.0 : glob.vals[static_cast<size_t>(hi + 1)];
    }
    return dist;
}
