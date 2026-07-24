#include "z9_val.h"

#include "profile.h"

#include <math.h>

static double tile_lambda(int tile, const struct model_spec *spec, double shift_add) {
    double lam = spec->diag[tile] + spec->shift + shift_add;
    if (tile > 0) {
        lam -= fabs(spec->off[tile - 1]);
    }
    if (tile + 1 < spec->n) {
        lam -= fabs(spec->off[tile]);
    }
    return lam;
}

double v9_elem_shift(int tile, const struct model_spec *spec, double dt, int profile_id, double shift_add) {
    double lam = tile_lambda(tile, spec, shift_add);
    double denom = 1.0 - dt * lam;
    if (fabs(denom) < 1.0e-18) {
        return 0.0;
    }
    double base = 1.0 / denom;
    double chain = log1p(dt * fabs(lam) * 0.1);
    return base * (1.0 + chain * profile_scale(profile_id));
}

double v9_elem(int tile, const struct model_spec *spec, double dt, int profile_id) {
    return v9_elem_shift(tile, spec, dt, profile_id, 0.0);
}

double v9_stab_shift(const struct model_spec *spec, double dt, double shift_add) {
    double rho = 0.0;
    for (int i = 0; i < spec->n; i++) {
        double lam = tile_lambda(i, spec, shift_add);
        double d = fabs(1.0 - dt * lam);
        if (d < 1.0e-18) {
            return 1.0e6;
        }
        double val = fabs(1.0 / d);
        if (val > rho) {
            rho = val;
        }
    }
    return rho;
}

double v9_stab(const struct model_spec *spec, double dt) {
    return v9_stab_shift(spec, dt, 0.0);
}
