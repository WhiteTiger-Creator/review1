#ifndef QDRIFT_TOPO_ORDER_H
#define QDRIFT_TOPO_ORDER_H

#include "qdrift/graph_model.h"

int qdrift_topo_sort(const qdrift_graph_t *g, int *order_out, int max_layers);

#endif
