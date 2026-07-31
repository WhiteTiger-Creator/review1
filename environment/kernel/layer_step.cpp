#include "qdrift/layer_step.h"

#include "qdrift/affine_kernel.h"
#include "qdrift/interval_ops.h"

void qdrift_layer_propagate(
    const qdrift_layer_t *layer,
    const qdrift_weight_t *weight,
    const qdrift_interval_t *in_ref,
    const qdrift_interval_t *in_quant,
    qdrift_interval_t *out_ref,
    qdrift_interval_t *out_quant
) {
    if (layer->op == QDRIFT_OP_AFFINE && weight) {
        qdrift_affine_propagate(in_ref, in_quant, weight, out_ref, out_quant);
        return;
    }
    if (layer->op == QDRIFT_OP_RELU) {
        *out_ref = qdrift_relu_interval(in_ref);
        *out_quant = qdrift_relu_interval(in_quant);
        return;
    }
    *out_ref = *in_ref;
    *out_quant = *in_quant;
}
