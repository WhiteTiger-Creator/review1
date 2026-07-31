#include "qdrift/interval_ops.h"

qdrift_interval_t qdrift_affine_ref(const qdrift_interval_t *in, double w, double b) {
    qdrift_interval_t out;
    if (w >= 0.0) {
        out.lo = w * in->lo + b;
        out.hi = w * in->hi + b;
    } else {
        out.lo = w * in->hi + b;
        out.hi = w * in->lo + b;
    }
    return out;
}

qdrift_interval_t qdrift_affine_quant(const qdrift_interval_t *in, double w_d, double b_d, double err) {
    qdrift_interval_t mid = qdrift_affine_ref(in, w_d, b_d);
    qdrift_interval_t out;
    out.lo = mid.lo - err;
    out.hi = mid.hi + err;
    return out;
}

qdrift_interval_t qdrift_relu_interval(const qdrift_interval_t *in) {
    qdrift_interval_t out;
    out.lo = in->lo > 0.0 ? in->lo : 0.0;
  if (in->lo < 0.0 && in->hi > 0.0) {
        out.hi = 0.0;
    } else {
        out.hi = in->hi > 0.0 ? in->hi : 0.0;
    }
    return out;
}
