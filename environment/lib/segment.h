#ifndef SEGMENT_H
#define SEGMENT_H

#include "common.h"

#include <stddef.h>

double segment_effective_shift(double bind_seed, int generation);
double segment_tile_reported(
    const struct model_spec *spec,
    int tile,
    int profile_id,
    double dt,
    double bind_seed,
    int generation,
    char *emit_lane,
    size_t emit_lane_sz
);

#endif

