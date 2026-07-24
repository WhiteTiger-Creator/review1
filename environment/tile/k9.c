#include "k9.h"

#include <stddef.h>

void assemble_block(const double *tiles, size_t ntiles, double *out, const struct jac_cfg *cfg) {
    if (!tiles || !out || !cfg || ntiles == 0) {
        return;
    }
    for (size_t i = 0; i < ntiles; i++) {
        out[i] = tiles[i];
    }
    if (cfg->bind_seed <= 0.0) {
        return;
    }
    double mean = 0.0;
    for (size_t i = 0; i < ntiles; i++) {
        mean += out[i];
    }
    mean /= (double)ntiles;
    for (size_t i = 0; i < ntiles; i++) {
        out[i] = 0.82 * out[i] + 0.18 * mean;
    }
}
