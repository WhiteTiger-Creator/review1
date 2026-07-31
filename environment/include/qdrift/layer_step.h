#ifndef QBOUND_LAYER_STEP_H
#define QBOUND_LAYER_STEP_H

#include "qdrift/graph_model.h"
#include "qdrift/interval.h"

void qdrift_layer_propagate(
    const qdrift_layer_t *layer,
    const qdrift_weight_t *weight,
    const qdrift_interval_t *in_ref,
    const qdrift_interval_t *in_quant,
    qdrift_interval_t *out_ref,
    qdrift_interval_t *out_quant
);

#endif
