#include "profile.h"

#include <string.h>

int q7_active_profile = 0;
static double q7_bind_seed = 0.0;
static int q7_generation = 0;

void profile_set_runtime(double bind_seed, int generation) {
    q7_bind_seed = bind_seed;
    q7_generation = generation;
}

double profile_bind_seed(void) {
    return q7_bind_seed;
}

int profile_generation(void) {
    return q7_generation;
}

void profile_set_active(int profile_id) {
    q7_active_profile = profile_id;
}

int profile_get_active(void) {
    return q7_active_profile;
}

double profile_scale(int profile_id) {
    if (profile_id == 1) {
        return 1.0 + 1.0e-7;
    }
    return 1.0;
}

int profile_id_from_name(const char *name) {
    if (name && strcmp(name, "scaled") == 0) {
        return 1;
    }
    return 0;
}

const char *profile_name_from_id(int profile_id) {
    return profile_id == 1 ? "scaled" : "nominal";
}
