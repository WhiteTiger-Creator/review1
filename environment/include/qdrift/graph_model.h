#ifndef QDRIFT_GRAPH_MODEL_H
#define QDRIFT_GRAPH_MODEL_H

#include "qdrift/interval.h"

#define QDRIFT_MAX_LAYERS 16
#define QDRIFT_MAX_ID_LEN 32
#define QDRIFT_MAX_WEIGHT_KEY 16

typedef enum {
    QDRIFT_OP_INPUT = 0,
    QDRIFT_OP_AFFINE,
    QDRIFT_OP_RELU,
    QDRIFT_OP_OUTPUT
} qdrift_op_t;

typedef struct {
    char id[QDRIFT_MAX_ID_LEN];
    qdrift_op_t op;
    char inputs[2][QDRIFT_MAX_ID_LEN];
    int input_count;
    char weight_key[QDRIFT_MAX_WEIGHT_KEY];
} qdrift_layer_t;

typedef struct {
    double w;
    double b;
    int has_quant;
    double scale;
    int zero_point;
    int w_q;
    int b_q;
} qdrift_weight_t;

typedef struct {
    char graph_id[64];
    int certification_epoch;
    qdrift_layer_t layers[QDRIFT_MAX_LAYERS];
    int layer_count;
    qdrift_weight_t weights[8];
    int weight_count;
    char weight_keys[8][QDRIFT_MAX_WEIGHT_KEY];
} qdrift_graph_t;

typedef struct {
    char variant_id[64];
    char graph_id[64];
} qdrift_variant_meta_t;

typedef struct {
    char scenario_id[64];
    double drift_bound;
    qdrift_interval_t input_interval;
} qdrift_scenario_t;

int qdrift_load_graph_pack(const char *root, qdrift_graph_t *out);
int qdrift_apply_variant(const char *variant_root, const char *variant_id, qdrift_graph_t *g);
int qdrift_apply_variant_file(const char *variant_path, qdrift_graph_t *g);
int qdrift_load_scenario(const char *root, const char *scenario_id, qdrift_scenario_t *out);
int qdrift_load_scenario_file(const char *path, qdrift_scenario_t *out);

#endif
