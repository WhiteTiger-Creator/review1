#ifndef STAGE_JAC_H
#define STAGE_JAC_H

#include "common.h"

#include <stddef.h>

void stage_jac_assemble(const double *tiles, size_t ntiles, double *out, const struct jac_cfg *cfg);

#endif
