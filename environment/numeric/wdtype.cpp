#include "qdrift/format_policy.h"

double qdrift_quant_half_width(const qdrift_weight_t *wt) {
    if (!wt->has_quant) {
        return 0.0;
    }
    return wt->scale;
}

void qdrift_dequant_weight(const qdrift_weight_t *wt, double *w_d, double *b_d) {
    if (!wt->has_quant) {
        *w_d = wt->w;
        *b_d = wt->b;
        return;
    }
    *w_d = (wt->w_q - wt->zero_point) * wt->scale;
    *b_d = (wt->b_q - wt->zero_point) * wt->scale;
}
