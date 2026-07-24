#include "stage_jac.h"

#include "k9.h"

void stage_jac_assemble(const double *tiles, size_t ntiles, double *out, const struct jac_cfg *cfg) {
    assemble_block(tiles, ntiles, out, cfg);
}
