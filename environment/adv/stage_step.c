#include "stage_step.h"

#include "w1.h"

int stage_step_advance(const double *J, const double *rhs, double dt, double *u, struct step_ctx *ctx) {
    return advance_u(J, rhs, dt, u, ctx);
}
