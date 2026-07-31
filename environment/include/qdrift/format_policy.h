#ifndef QDRIFT_FORMAT_POLICY_H
#define QDRIFT_FORMAT_POLICY_H

#include "qdrift/graph_model.h"

double qdrift_quant_half_width(const qdrift_weight_t *wt);
void qdrift_dequant_weight(const qdrift_weight_t *wt, double *w_d, double *b_d);

#endif
