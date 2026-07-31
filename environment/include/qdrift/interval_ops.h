#ifndef QDRIFT_INTERVAL_OPS_H
#define QDRIFT_INTERVAL_OPS_H

#include "qdrift/interval.h"

qdrift_interval_t qdrift_affine_ref(const qdrift_interval_t *in, double w, double b);
qdrift_interval_t qdrift_affine_quant(const qdrift_interval_t *in, double w_d, double b_d, double err);
qdrift_interval_t qdrift_relu_interval(const qdrift_interval_t *in);

#endif
