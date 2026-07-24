#ifndef Z9_VAL_H
#define Z9_VAL_H

#include "common.h"

double v9_elem(int tile, const struct model_spec *spec, double dt, int profile_id);
double v9_elem_shift(int tile, const struct model_spec *spec, double dt, int profile_id, double shift_add);
double v9_stab(const struct model_spec *spec, double dt);
double v9_stab_shift(const struct model_spec *spec, double dt, double shift_add);

#endif
