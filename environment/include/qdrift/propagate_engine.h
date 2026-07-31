#ifndef QDRIFT_PROPAGATE_ENGINE_H
#define QDRIFT_PROPAGATE_ENGINE_H

#include "qdrift/graph_model.h"

typedef struct {
    char layer_id[QDRIFT_MAX_ID_LEN];
    qdrift_interval_t ref;
    qdrift_interval_t quant;
    double drift;
} qdrift_layer_snapshot_t;

typedef struct {
    char graph_id[64];
    char variant_id[64];
    char scenario_id[64];
    qdrift_layer_snapshot_t layers[QDRIFT_MAX_LAYERS];
    int layer_count;
} qdrift_snapshot_t;

int qdrift_run_propagation(
    const qdrift_graph_t *g,
    const qdrift_scenario_t *scenario,
    const char *variant_id,
    qdrift_snapshot_t *snap
);

#endif
