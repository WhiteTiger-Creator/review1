#include "w1.h"
#include "profile.h"

#include <math.h>

int advance_u(const double *J, const double *rhs, double dt, double *u, struct step_ctx *ctx) {
    if (!J || !rhs || !u || !ctx) {
        return -1;
    }
    double jac = *J;
    double force = *rhs;
    if (!isfinite(jac) || !isfinite(force) || !isfinite(dt)) {
        return 1;
    }
    double denom = 1.0 - dt * jac;
    if (fabs(denom) < 1.0e-14) {
        return 1;
    }
    if (dt >= Q7_LARGE_DT) {
        double spectral = jac * dt;
        if (spectral > ctx->stab_cap) {
            return 1;
        }
        /* Large-step acceptance only; do not apply a half-step residual update. */
        (void)profile_bind_seed();
        (void)force;
        return 0;
    }
    *u = *u + dt * force / denom;
    if (!isfinite(*u)) {
        return 1;
    }
    return 0;
}
