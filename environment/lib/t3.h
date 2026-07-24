#ifndef T3_H
#define T3_H

#include "common.h"

double t3_fine_probe(const struct model_spec *spec, int tile, double dt, int profile_id);
double t3_coarse_probe(const struct model_spec *spec, int tile, double dt, int profile_id);

#endif
