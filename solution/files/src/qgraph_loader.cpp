#include "qdrift/graph_model.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_file(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) {
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    fread(buf, 1, (size_t)sz, f);
    buf[sz] = '\0';
    fclose(f);
    return buf;
}

static const char *find_key(const char *json, const char *key) {
    char pat[128];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    return strstr(json, pat);
}

static int parse_string_after(const char *json, const char *key, char *out, int out_len) {
    const char *p = find_key(json, key);
    if (!p) {
        return 0;
    }
    p = strchr(p, ':');
    if (!p) {
        return 0;
    }
    p = strchr(p, '"');
    if (!p) {
        return 0;
    }
    ++p;
    const char *e = strchr(p, '"');
    if (!e) {
        return 0;
    }
    int n = (int)(e - p);
    if (n >= out_len) {
        n = out_len - 1;
    }
    memcpy(out, p, (size_t)n);
    out[n] = '\0';
    return 1;
}

static double parse_number_after(const char *json, const char *key) {
    const char *p = find_key(json, key);
    if (!p) {
        return 0.0;
    }
    p = strchr(p, ':');
    if (!p) {
        return 0.0;
    }
    return strtod(p + 1, NULL);
}

static int parse_int_after(const char *json, const char *key) {
    return (int)parse_number_after(json, key);
}

static qdrift_op_t parse_op(const char *s) {
    if (strcmp(s, "input") == 0) {
        return QDRIFT_OP_INPUT;
    }
    if (strcmp(s, "affine") == 0) {
        return QDRIFT_OP_AFFINE;
    }
    if (strcmp(s, "relu") == 0) {
        return QDRIFT_OP_RELU;
    }
    return QDRIFT_OP_OUTPUT;
}

static const char *json_object_end(const char *start) {
    int depth = 0;
    for (const char *c = start; *c != '\0'; ++c) {
        if (*c == '{') {
            depth++;
        } else if (*c == '}') {
            depth--;
            if (depth == 0) {
                return c;
            }
        }
    }
    return NULL;
}

static int load_layers(const char *json, qdrift_graph_t *g) {
    const char *p = strstr(json, "\"layers\"");
    if (!p) {
        return 0;
    }
    p = strchr(p, '[');
    if (!p) {
        return 0;
    }
    g->layer_count = 0;
    while (g->layer_count < QDRIFT_MAX_LAYERS) {
        const char *obj = strchr(p, '{');
        if (!obj) {
            break;
        }
        const char *end = json_object_end(obj);
        if (!end) {
            break;
        }
        char block[512];
        int len = (int)(end - obj + 1);
        if (len >= (int)sizeof(block)) {
            len = (int)sizeof(block) - 1;
        }
        memcpy(block, obj, (size_t)len);
        block[len] = '\0';
        qdrift_layer_t *L = &g->layers[g->layer_count];
        memset(L, 0, sizeof(*L));
        parse_string_after(block, "id", L->id, sizeof(L->id));
        char op[32];
        if (parse_string_after(block, "op", op, sizeof(op))) {
            L->op = parse_op(op);
        }
        parse_string_after(block, "weight_key", L->weight_key, sizeof(L->weight_key));
        const char *inp = find_key(block, "inputs");
        L->input_count = 0;
        if (inp) {
            const char *br = strchr(inp, '[');
            if (br) {
                const char *q = strchr(br, '"');
                if (q) {
                    ++q;
                    const char *qe = strchr(q, '"');
                    if (qe) {
                        int n = (int)(qe - q);
                        if (n < QDRIFT_MAX_ID_LEN) {
                            memcpy(L->inputs[0], q, (size_t)n);
                            L->inputs[0][n] = '\0';
                            L->input_count = 1;
                        }
                    }
                }
            }
        }
        g->layer_count++;
        p = end + 1;
        if (!strchr(p, '{')) {
            break;
        }
    }
    return 1;
}

static void add_weight(qdrift_graph_t *g, const char *key, double w, double b) {
    strncpy(g->weight_keys[g->weight_count], key, QDRIFT_MAX_WEIGHT_KEY - 1);
    g->weights[g->weight_count].w = w;
    g->weights[g->weight_count].b = b;
    g->weights[g->weight_count].has_quant = 0;
    g->weight_count++;
}

static int parse_weight_block(const char *key, const char *block, qdrift_graph_t *g) {
    if (!strstr(block, "\"w\"")) {
        return 0;
    }
    add_weight(g, key, parse_number_after(block, "w"), parse_number_after(block, "b"));
    return 1;
}

static int parse_top_level_weight_objects(const char *json, qdrift_graph_t *g) {
    const char *start = strchr(json, '{');
    if (!start) {
        return 0;
    }
    const char *p = start + 1;
    while (g->weight_count < 8) {
        while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t' || *p == ',') {
            p++;
        }
        if (*p == '}') {
            break;
        }
        if (*p != '"') {
            break;
        }
        p++;
        const char *key_end = strchr(p, '"');
        if (!key_end) {
            break;
        }
        char key[QDRIFT_MAX_WEIGHT_KEY];
        int kn = (int)(key_end - p);
        if (kn >= QDRIFT_MAX_WEIGHT_KEY) {
            kn = QDRIFT_MAX_WEIGHT_KEY - 1;
        }
        memcpy(key, p, (size_t)kn);
        key[kn] = '\0';
        p = key_end + 1;
        const char *obj = strchr(p, '{');
        if (!obj) {
            break;
        }
        const char *end = json_object_end(obj);
        if (!end) {
            break;
        }
        char block[512];
        int len = (int)(end - obj + 1);
        if (len >= (int)sizeof(block)) {
            len = (int)sizeof(block) - 1;
        }
        memcpy(block, obj, (size_t)len);
        block[len] = '\0';
        parse_weight_block(key, block, g);
        p = end + 1;
    }
    return 1;
}

static int load_weights(const char *json, qdrift_graph_t *g) {
    g->weight_count = 0;
    return parse_top_level_weight_objects(json, g);
}

int qdrift_load_graph_pack(const char *root, qdrift_graph_t *out) {
    char path[512];
    snprintf(path, sizeof(path), "%s/graph.json", root);
    char *gj = read_file(path);
    if (!gj) {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    parse_string_after(gj, "graph_id", out->graph_id, sizeof(out->graph_id));
    out->certification_epoch = parse_int_after(gj, "certification_epoch");
    load_layers(gj, out);
    free(gj);
    snprintf(path, sizeof(path), "%s/weights.json", root);
    char *wj = read_file(path);
    if (!wj) {
        return -1;
    }
    load_weights(wj, out);
    free(wj);
    return 0;
}

static qdrift_weight_t *find_weight(qdrift_graph_t *g, const char *key) {
    for (int i = 0; i < g->weight_count; ++i) {
        if (strcmp(g->weight_keys[i], key) == 0) {
            return &g->weights[i];
        }
    }
    return NULL;
}

static int apply_variant_json(const char *vj, qdrift_graph_t *g) {
    const char *ov = strstr(vj, "\"overrides\"");
    if (!ov) {
        return 0;
    }
    const char *colon = strchr(ov, ':');
    if (!colon) {
        return 0;
    }
    const char *obj = strchr(colon, '{');
    if (!obj) {
        return 0;
    }
    const char *end = json_object_end(obj);
    if (!end) {
        return 0;
    }
    char overrides[2048];
    int len = (int)(end - obj + 1);
    if (len >= (int)sizeof(overrides)) {
        len = (int)sizeof(overrides) - 1;
    }
    memcpy(overrides, obj, (size_t)len);
    overrides[len] = '\0';
    const char *p = overrides + 1;
    while (p < overrides + len) {
        while (p < overrides + len && (*p == ' ' || *p == '\n' || *p == ',')) {
            p++;
        }
        if (*p == '}') {
            break;
        }
        if (*p != '"') {
            break;
        }
        p++;
        const char *key_end = strchr(p, '"');
        if (!key_end) {
            break;
        }
        char key[QDRIFT_MAX_WEIGHT_KEY];
        int kn = (int)(key_end - p);
        if (kn >= QDRIFT_MAX_WEIGHT_KEY) {
            kn = QDRIFT_MAX_WEIGHT_KEY - 1;
        }
        memcpy(key, p, (size_t)kn);
        key[kn] = '\0';
        p = key_end + 1;
        const char *entry = strchr(p, '{');
        if (!entry) {
            break;
        }
        const char *entry_end = json_object_end(entry);
        if (!entry_end) {
            break;
        }
        char block[512];
        int blen = (int)(entry_end - entry + 1);
        if (blen >= (int)sizeof(block)) {
            blen = (int)sizeof(block) - 1;
        }
        memcpy(block, entry, (size_t)blen);
        block[blen] = '\0';
        if (!strstr(block, "\"dtype\"")) {
            p = entry_end + 1;
            continue;
        }
        qdrift_weight_t *w = find_weight(g, key);
        if (w) {
            w->has_quant = 1;
            w->scale = parse_number_after(block, "scale");
            w->zero_point = parse_int_after(block, "zero_point");
            w->w_q = parse_int_after(block, "w_q");
            w->b_q = parse_int_after(block, "b_q");
        }
        p = entry_end + 1;
    }
    return 0;
}

int qdrift_apply_variant_file(const char *variant_path, qdrift_graph_t *g) {
    char *vj = read_file(variant_path);
    if (!vj) {
        return -1;
    }
    int rc = apply_variant_json(vj, g);
    free(vj);
    return rc;
}

int qdrift_apply_variant(const char *variant_root, const char *variant_id, qdrift_graph_t *g) {
    char path[512];
    snprintf(path, sizeof(path), "%s/%s/variant.json", variant_root, variant_id);
    return qdrift_apply_variant_file(path, g);
}

int qdrift_load_scenario(const char *root, const char *scenario_id, qdrift_scenario_t *out) {
    char path[512];
    snprintf(path, sizeof(path), "%s/%s/scenario.json", root, scenario_id);
    return qdrift_load_scenario_file(path, out);
}

int qdrift_load_scenario_file(const char *path, qdrift_scenario_t *out) {
    char *sj = read_file(path);
    if (!sj) {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    parse_string_after(sj, "scenario_id", out->scenario_id, sizeof(out->scenario_id));
    out->drift_bound = parse_number_after(sj, "drift_bound");
    const char *ii = strstr(sj, "\"input_interval\"");
    if (ii) {
        out->input_interval.lo = parse_number_after(ii, "lo");
        out->input_interval.hi = parse_number_after(ii, "hi");
    }
    free(sj);
    return 0;
}
