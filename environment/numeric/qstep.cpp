#include "qdrift/affine_kernel.h"

#include "qdrift/format_policy.h"
#include "qdrift/interval_ops.h"

void qdrift_affine_propagate(
    const qdrift_interval_t *in_ref,
    const qdrift_interval_t *in_quant,
    const qdrift_weight_t *wt,
    qdrift_interval_t *out_ref,
    qdrift_interval_t *out_quant
) {
    *out_ref = qdrift_affine_ref(in_ref, wt->w, wt->b);
    double w_d = 0.0;
    double b_d = 0.0;
    qdrift_dequant_weight(wt, &w_d, &b_d);
    double half = qdrift_quant_half_width(wt);
    double err = half;
    *out_quant = qdrift_affine_quant(in_quant, w_d, b_d, err);
}
