#include "qdrift/topo_order.h"

#include <string.h>

static int layer_index_by_id(const qdrift_graph_t *g, const char *id) {
    for (int i = 0; i < g->layer_count; ++i) {
        if (strcmp(g->layers[i].id, id) == 0) {
            return i;
        }
    }
    return -1;
}

/* Topological layer walk sequence for interval propagation */
int qdrift_topo_sort(const qdrift_graph_t *g, int *order_out, int max_layers) {
    int n = g->layer_count < max_layers ? g->layer_count : max_layers;
    int order[QDRIFT_MAX_LAYERS];
    for (int i = 0; i < n; ++i) {
        order[i] = i;
    }
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            if (strcmp(g->layers[order[i]].id, g->layers[order[j]].id) > 0) {
                int tmp = order[i];
                order[i] = order[j];
                order[j] = tmp;
            }
        }
    }
    for (int i = 0; i < n; ++i) {
        order_out[i] = order[i];
    }
    return n;
}

int qdrift_topo_layer_index(const qdrift_graph_t *g, const char *id) {
    return layer_index_by_id(g, id);
}
