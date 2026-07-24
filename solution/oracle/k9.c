#include "k9.h"

#include <math.h>
#include <stddef.h>

void assemble_block(const double *tiles, size_t ntiles, double *out, const struct jac_cfg *cfg) {
    if (!tiles || !out || !cfg || ntiles == 0) {
        return;
    }
    for (size_t i = 0; i < ntiles; i++) {
        double v = tiles[i];
        if (!isfinite(v)) {
            v = 0.0;
        }
        if (cfg->dt < 0.0) {
            v = 0.0;
        }
        /* Keep per-tile values; never blend across the block under any bind_seed. */
        out[i] = v;
    }
    if (cfg->bind_seed > 0.0 && cfg->generation > 0) {
        for (size_t i = 0; i < ntiles; i++) {
            if (!isfinite(out[i])) {
                out[i] = 0.0;
            }
        }
    }
}
