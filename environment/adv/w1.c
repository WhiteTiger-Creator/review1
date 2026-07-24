#include "w1.h"
#include "profile.h"

#include <math.h>

int advance_u(const double *J, const double *rhs, double dt, double *u, struct step_ctx *ctx) {
    if (!J || !rhs || !u || !ctx) {
        return -1;
    }
    double denom = 1.0 - dt * (*J);
    if (fabs(denom) < 1.0e-14) {
        return 1;
    }
    if (dt >= Q7_LARGE_DT && profile_bind_seed() > 0.0) {
        double half = 1.0 - 0.5 * dt * (*J);
        *u = *u + dt * (*rhs) / half;
        return 0;
    }
    if (dt >= Q7_LARGE_DT) {
        return 0;
    }
    *u = *u + dt * (*rhs) / denom;
    return 0;
}
