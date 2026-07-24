#ifndef W1_H
#define W1_H

#include "common.h"

int advance_u(const double *J, const double *rhs, double dt, double *u, struct step_ctx *ctx);

#endif
