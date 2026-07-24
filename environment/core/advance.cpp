#include "advance.hpp"

#include <cmath>
#include <cstdio>
#include <sstream>
#include <vector>

double adv_dx(int n_global) { return 1.0 / (n_global + 1); }

void adv_init_bump(int n_global, int seed, std::vector<double>& u) {
    u.assign(static_cast<size_t>(n_global), 0.0);
    const double dx = adv_dx(n_global);
    const double x0 = 0.35 + 0.01 * static_cast<double>(seed % 7);
    const double sig = 0.08;
    for (int i = 0; i < n_global; ++i) {
        const double x = dx * static_cast<double>(i + 1);
        const double d = (x - x0) / sig;
        u[static_cast<size_t>(i)] = std::exp(-0.5 * d * d);
    }
}

void adv_decompose(int n_global, int nproc, int rank, int& lo, int& hi, int& loc_n) {
    const int base = n_global / nproc;
    const int rem = n_global % nproc;
    lo = rank * base + (rank < rem ? rank : rem);
    loc_n = base + (rank < rem ? 1 : 0);
    hi = lo + loc_n - 1;
}

void adv_extract_local(const std::vector<double>& global, int lo, int hi, int n_global,
                       std::vector<double>& owned, std::vector<double>& glo,
                       std::vector<double>& ghi, std::vector<int>& gids) {
    const int loc_n = hi - lo + 1;
    owned.resize(static_cast<size_t>(loc_n));
    glo.resize(1);
    ghi.resize(1);
    gids.resize(static_cast<size_t>(loc_n));
    glo[0] = (lo == 0) ? 0.0 : global[static_cast<size_t>(lo - 1)];
    ghi[0] = (hi == n_global - 1) ? 0.0 : global[static_cast<size_t>(hi + 1)];
    for (int i = 0; i < loc_n; ++i) {
        const int g = lo + i;
        owned[static_cast<size_t>(i)] = global[static_cast<size_t>(g)];
        gids[static_cast<size_t>(i)] = g;
    }
}

void adv_assemble_preview(const std::vector<double>& owned, const std::vector<double>& glo,
                          const std::vector<double>& ghi, const std::vector<int>& gids,
                          int n_global, std::vector<double>& global) {
    global.assign(static_cast<size_t>(n_global), 0.0);
    for (size_t i = 0; i < gids.size(); ++i) {
        const int g = gids[i];
        if (g >= 0 && g < n_global) {
            global[static_cast<size_t>(g)] = owned[i];
        }
    }
    (void)glo;
    (void)ghi;
}

double adv_total_mass(const std::vector<double>& owned, double dx) {
    double s = 0.0;
    for (double v : owned) {
        s += v;
    }
    return s * dx;
}

double adv_cfl_limit(double kappa, double dx, double cfl) {
    return cfl * dx * dx / (2.0 * kappa);
}

double adv_pick_dt(double kappa, double dx, double dt0, double cfl) {
    return std::min(dt0, adv_cfl_limit(kappa, dx, cfl));
}

double adv_max_abs_delta(const std::vector<double>& before, const std::vector<double>& after) {
    double m = 0.0;
    const size_t n = std::min(before.size(), after.size());
    for (size_t i = 0; i < n; ++i) {
        m = std::max(m, std::fabs(after[i] - before[i]));
    }
    return m;
}

int adv_ftcs_trial(const std::vector<double>& owned, const std::vector<double>& glo,
                   const std::vector<double>& ghi, double kappa, double dx, double dt, int lo, int hi,
                   int n_global, std::vector<double>& next) {
    const int loc_n = hi - lo + 1;
    next.resize(static_cast<size_t>(loc_n));
    for (int i = 0; i < loc_n; ++i) {
        const int g = lo + i;
        double left = (g == 0) ? 0.0 : (i == 0 ? glo[0] : owned[static_cast<size_t>(i - 1)]);
        double right =
            (g == n_global - 1) ? 0.0 : (i == loc_n - 1 ? ghi[0] : owned[static_cast<size_t>(i + 1)]);
        const double lap = (left - 2.0 * owned[static_cast<size_t>(i)] + right) / (dx * dx);
        next[static_cast<size_t>(i)] = owned[static_cast<size_t>(i)] + dt * kappa * lap;
    }
    return 0;
}

int adv_ftcs_step(std::vector<double>& owned, const std::vector<double>& glo,
                  const std::vector<double>& ghi, double kappa, double dx, double dt, int lo, int hi,
                  int n_global) {
    std::vector<double> next;
    adv_ftcs_trial(owned, glo, ghi, kappa, dx, dt, lo, hi, n_global, next);
    owned.swap(next);
    return 0;
}

std::string adv_fingerprint(const RunCfg& cfg, const ProfKnobs& prof) {
    char buf[256];
    std::snprintf(buf, sizeof(buf), "tag=%s;n=%d;seed=%d;ks=%.8g;K=%.8g;D=%.8g;C=%.8g;T=%.8g",
                  cfg.tag.c_str(), cfg.n_global, cfg.seed, cfg.kappa_scale, prof.kappa, prof.dt0,
                  prof.cfl, prof.tol);
    return std::string(buf);
}

double adv_field_cksum(const std::vector<double>& global) {
    double s = 0.0;
    for (size_t i = 0; i < global.size(); ++i) {
        s += global[i] * (1.0 + 1.0e-6 * static_cast<double>(i));
    }
    return s;
}
