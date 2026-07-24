#ifndef Q7_PROFILE_H
#define Q7_PROFILE_H

#include "common.h"

void profile_set_active(int profile_id);
int profile_get_active(void);
double profile_scale(int profile_id);
void profile_set_runtime(double bind_seed, int generation);
double profile_bind_seed(void);
int profile_generation(void);

#endif
