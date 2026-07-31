#include "qdrift/propagate_engine.h"

#include "qdrift/interval.h"
#include "qdrift/layer_step.h"
#include "qdrift/topo_order.h"

#include <string.h>

static const qdrift_weight_t *weight_for_layer(const qdrift_graph_t *g, const qdrift_layer_t *L) {
    for (int i = 0; i < g->weight_count; ++i) {
        if (strcmp(g->weight_keys[i], L->weight_key) == 0) {
            return &g->weights[i];
        }
    }
    return NULL;
}

static int find_snapshot_layer(qdrift_snapshot_t *snap, const char *id) {
    for (int i = 0; i < snap->layer_count; ++i) {
        if (strcmp(snap->layers[i].layer_id, id) == 0) {
            return i;
        }
    }
    return -1;
}

int qdrift_run_propagation(
    const qdrift_graph_t *g,
    const qdrift_scenario_t *scenario,
    const char *variant_id,
    qdrift_snapshot_t *snap
) {
    memset(snap, 0, sizeof(*snap));
    strncpy(snap->graph_id, g->graph_id, sizeof(snap->graph_id) - 1);
    strncpy(snap->variant_id, variant_id, sizeof(snap->variant_id) - 1);
    strncpy(snap->scenario_id, scenario->scenario_id, sizeof(snap->scenario_id) - 1);

    int order[QDRIFT_MAX_LAYERS];
    int n = qdrift_topo_sort(g, order, QDRIFT_MAX_LAYERS);

    for (int oi = 0; oi < n; ++oi) {
        const qdrift_layer_t *L = &g->layers[order[oi]];
        qdrift_layer_snapshot_t *row = &snap->layers[snap->layer_count++];
        strncpy(row->layer_id, L->id, sizeof(row->layer_id) - 1);

        qdrift_interval_t in_ref = {0.0, 0.0};
        qdrift_interval_t in_quant = {0.0, 0.0};
        if (L->op == QDRIFT_OP_INPUT) {
            in_ref = scenario->input_interval;
            in_quant = scenario->input_interval;
        } else if (L->input_count > 0) {
            int pi = find_snapshot_layer(snap, L->inputs[0]);
            if (pi < 0) {
                return -1;
            }
            in_ref = snap->layers[pi].ref;
            in_quant = snap->layers[pi].quant;
        }

        if (L->op == QDRIFT_OP_INPUT) {
            row->ref = in_ref;
            row->quant = in_quant;
        } else {
            const qdrift_weight_t *wt = (L->op == QDRIFT_OP_AFFINE) ? weight_for_layer(g, L) : NULL;
            if (L->op == QDRIFT_OP_AFFINE && !wt) {
                return -1;
            }
            qdrift_layer_propagate(L, wt, &in_ref, &in_quant, &row->ref, &row->quant);
        }
        row->drift = qdrift_interval_drift(&row->ref, &row->quant);
    }
    return 0;
}
