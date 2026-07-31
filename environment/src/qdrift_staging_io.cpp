#include "qdrift/staging_io.h"

#include <cstdlib>
#include <stdio.h>
#include <string.h>

int qdrift_write_pack_context(
    const char *staging_dir,
    const char *graph_id,
    const char *variant_id,
    const char *scenario_id,
    int certification_epoch
) {
    char path[512];
    snprintf(path, sizeof(path), "%s/pack-context.json", staging_dir);
    FILE *f = fopen(path, "w");
    if (!f) {
        return -1;
    }
    fprintf(
        f,
        "{\"graph_id\":\"%s\",\"variant_id\":\"%s\",\"scenario_id\":\"%s\",\"certification_epoch\":%d}\n",
        graph_id,
        variant_id,
        scenario_id,
        certification_epoch
    );
    fclose(f);
    return 0;
}

int qdrift_write_snapshot(const char *staging_dir, const qdrift_snapshot_t *snap) {
    char path[512];
    snprintf(path, sizeof(path), "%s/layer-intervals.json", staging_dir);
    FILE *f = fopen(path, "w");
    if (!f) {
        return -1;
    }
    fprintf(f, "{\n");
    fprintf(f, "  \"graph_id\": \"%s\",\n", snap->graph_id);
    fprintf(f, "  \"variant_id\": \"%s\",\n", snap->variant_id);
    fprintf(f, "  \"scenario_id\": \"%s\",\n", snap->scenario_id);
    fprintf(f, "  \"layers\": [\n");
    for (int i = 0; i < snap->layer_count; ++i) {
        const qdrift_layer_snapshot_t *L = &snap->layers[i];
        fprintf(
            f,
            "    {\"layer_id\": \"%s\", \"ref\": {\"lo\": %.6f, \"hi\": %.6f}, "
            "\"quant\": {\"lo\": %.6f, \"hi\": %.6f}, \"drift\": %.6f}%s\n",
            L->layer_id,
            L->ref.lo,
            L->ref.hi,
            L->quant.lo,
            L->quant.hi,
            L->drift,
            i + 1 < snap->layer_count ? "," : ""
        );
    }
    fprintf(f, "  ]\n}\n");
    fclose(f);
    return 0;
}

static double parse_layer_field(const char *block, const char *field) {
    if (!block) {
        return 0.0;
    }
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", field);
    const char *p = strstr(block, pat);
    if (!p) {
        return 0.0;
    }
    p = strchr(p, ':');
    if (!p) {
        return 0.0;
    }
    return strtod(p + 1, NULL);
}

static void parse_string_field(const char *buf, const char *key, char *out, int out_len) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(buf, pat);
    if (!p) {
        return;
    }
    p = strchr(p, ':');
    if (!p) {
        return;
    }
    p = strchr(p, '"');
    if (!p) {
        return;
    }
    p++;
    const char *end = strchr(p, '"');
    if (!end) {
        return;
    }
    int n = (int)(end - p);
    if (n >= out_len) {
        n = out_len - 1;
    }
    memcpy(out, p, (size_t)n);
    out[n] = '\0';
}

static const char *layer_object_end(const char *start) {
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

int qdrift_read_snapshot(const char *staging_dir, qdrift_snapshot_t *snap) {
    char path[512];
    snprintf(path, sizeof(path), "%s/layer-intervals.json", staging_dir);
    FILE *f = fopen(path, "r");
    if (!f) {
        return -1;
    }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = (char *)malloc((size_t)sz + 1);
    fread(buf, 1, (size_t)sz, f);
    buf[sz] = '\0';
    fclose(f);
    memset(snap, 0, sizeof(*snap));
    parse_string_field(buf, "graph_id", snap->graph_id, (int)sizeof(snap->graph_id));
    parse_string_field(buf, "variant_id", snap->variant_id, (int)sizeof(snap->variant_id));
    parse_string_field(buf, "scenario_id", snap->scenario_id, (int)sizeof(snap->scenario_id));
    const char *layers = strstr(buf, "\"layers\"");
    if (!layers) {
        free(buf);
        return -1;
    }
    const char *p = layers;
    snap->layer_count = 0;
    while ((p = strstr(p, "\"layer_id\"")) != NULL && snap->layer_count < QDRIFT_MAX_LAYERS) {
        const char *start = p;
        while (start > buf && *start != '{') {
            start--;
        }
        const char *end = layer_object_end(start);
        if (!end) {
            break;
        }
        char block[512];
        int len = (int)(end - start + 1);
        if (len >= (int)sizeof(block)) {
            len = (int)sizeof(block) - 1;
        }
        memcpy(block, start, (size_t)len);
        block[len] = '\0';
        qdrift_layer_snapshot_t *L = &snap->layers[snap->layer_count++];
        const char *idp = strstr(block, "\"layer_id\"");
        if (!idp) {
            break;
        }
        idp = strchr(idp, ':');
        if (!idp) {
            break;
        }
        idp = strchr(idp, '"');
        if (!idp) {
            break;
        }
        idp++;
        const char *ide = strchr(idp, '"');
        if (!ide) {
            break;
        }
        int n = (int)(ide - idp);
        if (n >= QDRIFT_MAX_ID_LEN) {
            n = QDRIFT_MAX_ID_LEN - 1;
        }
        memcpy(L->layer_id, idp, (size_t)n);
        L->layer_id[n] = '\0';
        const char *ref = strstr(block, "\"ref\"");
        L->ref.lo = parse_layer_field(ref, "lo");
        L->ref.hi = parse_layer_field(ref, "hi");
        const char *quant = strstr(block, "\"quant\"");
        L->quant.lo = parse_layer_field(quant, "lo");
        L->quant.hi = parse_layer_field(quant, "hi");
        L->drift = parse_layer_field(block, "drift");
        p = end + 1;
    }
    free(buf);
    return 0;
}
