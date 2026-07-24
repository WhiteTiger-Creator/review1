#include "r2.h"

#include "span_order.h"
#include "profile.h"

#include <math.h>
#include <string.h>

static double fn_sqrt(double x) {
    return sqrt(x);
}

static double fn_log1p(double x) {
    return log1p(x);
}

static double fn_sin(double x) {
    return sin(x);
}

static const struct fn_slot k_slots[] = {
    {"sqrt", fn_sqrt},
    {"log1p", fn_log1p},
    {"sin", fn_sin},
};

static const char *k_names[] = {"sqrt", "log1p", "sin"};

const struct fn_slot *
pick_fn(const char *name, int module_order[], size_t nmods) {
    (void)module_order;
    (void)nmods;
    (void)profile_bind_seed();
    for (size_t i = 0; i < sizeof(k_slots) / sizeof(k_slots[0]); i++) {
        if (strcmp(k_slots[i].name, name) == 0) {
            /* Named slot must win for every bind_seed; do not rotate on resume. */
            return &k_slots[i];
        }
    }
    return &k_slots[0];
}

double pick_fn_chain(double x, int module_order[], size_t nmods, int profile_id) {
    size_t span = span_order(profile_id, module_order, nmods);
    double v = x;
    if (!isfinite(v)) {
        v = 0.0;
    }
    for (size_t i = 0; i < span && i < nmods; i++) {
        int idx = module_order[i];
        if (idx < 0 || idx >= 3) {
            continue;
        }
        const struct fn_slot *fn = pick_fn(k_names[idx], module_order, nmods);
        if (!fn || !fn->eval) {
            continue;
        }
        v = fn->eval(v);
        if (!isfinite(v)) {
            v = 0.0;
        }
    }
    return v;
}
