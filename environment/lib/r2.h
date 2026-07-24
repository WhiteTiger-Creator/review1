#ifndef R2_H
#define R2_H

#include <stddef.h>

struct fn_slot {
    const char *name;
    double (*eval)(double);
};

const struct fn_slot *pick_fn(const char *name, int module_order[], size_t nmods);
double pick_fn_chain(double x, int module_order[], size_t nmods, int profile_id);

#endif
