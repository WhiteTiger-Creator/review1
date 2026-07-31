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

static int deps_satisfied(const qdrift_graph_t *g, int idx, const int *done, int done_n) {
    const qdrift_layer_t *L = &g->layers[idx];
    for (int i = 0; i < L->input_count; ++i) {
        int dep = layer_index_by_id(g, L->inputs[i]);
        int found = 0;
        for (int j = 0; j < done_n; ++j) {
            if (done[j] == dep) {
                found = 1;
                break;
            }
        }
        if (!found) {
            return 0;
        }
    }
    return 1;
}

int qdrift_topo_sort(const qdrift_graph_t *g, int *order_out, int max_layers) {
    int n = g->layer_count < max_layers ? g->layer_count : max_layers;
    int done[QDRIFT_MAX_LAYERS];
    int done_n = 0;
    int out_n = 0;
    while (out_n < n) {
        int progressed = 0;
        for (int i = 0; i < n; ++i) {
            int used = 0;
            for (int j = 0; j < out_n; ++j) {
                if (order_out[j] == i) {
                    used = 1;
                    break;
                }
            }
            if (used) {
                continue;
            }
            if (deps_satisfied(g, i, done, done_n)) {
                order_out[out_n++] = i;
                done[done_n++] = i;
                progressed = 1;
            }
        }
        if (!progressed) {
            return -1;
        }
    }
    return out_n;
}
