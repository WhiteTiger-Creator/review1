#ifndef STAGE_STEP_H
#define STAGE_STEP_H

#include "common.h"

int stage_step_advance(const double *J, const double *rhs, double dt, double *u, struct step_ctx *ctx);

#endif
