#include "t3.h"

#include "n3.h"
#include "z9_val.h"

double t3_fine_probe(const struct model_spec *spec, int tile, double dt, int profile_id) {
    double h = dt * 0.25;
    double f0 = v9_elem(tile, spec, dt, profile_id);
    double f1 = v9_elem(tile, spec, dt + h, profile_id);
    return n3_fd_probe(f0, f1, h);
}

double t3_coarse_probe(const struct model_spec *spec, int tile, double dt, int profile_id) {
    double h = dt;
    double f0 = v9_elem(tile, spec, dt, profile_id);
    double f1 = v9_elem(tile, spec, dt + h * 0.5, profile_id);
    return n3_fd_probe(f0, f1, h);
}
