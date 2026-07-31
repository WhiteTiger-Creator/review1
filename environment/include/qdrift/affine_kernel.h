#ifndef QDRIFT_AFFINE_KERNEL_H
#define QDRIFT_AFFINE_KERNEL_H

#include "qdrift/graph_model.h"
#include "qdrift/interval.h"

void qdrift_affine_propagate(
    const qdrift_interval_t *in_ref,
    const qdrift_interval_t *in_quant,
    const qdrift_weight_t *wt,
    qdrift_interval_t *out_ref,
    qdrift_interval_t *out_quant
);

#endif
