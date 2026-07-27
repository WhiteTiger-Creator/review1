#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return NULL;
    }
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    long sz = ftell(f);
    if (sz < 0) {
        fclose(f);
        return NULL;
    }
    if (fseek(f, 0, SEEK_SET) != 0) {
        fclose(f);
        return NULL;
    }
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    size_t n = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    buf[n] = '\0';
    if (out_len) {
        *out_len = n;
    }
    return buf;
}

int load_metrics(const char *tree_path, MetricRow *rows, int *n_rows) {
    char path[SHIP_MAX_PATH];
    snprintf(path, sizeof(path), "%s/metrics.json", tree_path);
    size_t len = 0;
    char *raw = read_file(path, &len);
    if (!raw) {
        *n_rows = 0;
        return -1;
    }
    int n = 0;
    const char *p = raw;
    while ((p = strstr(p, "\"k\"")) != NULL && n < SHIP_MAX_ROWS) {
        const char *colon = strchr(p, ':');
        if (!colon) {
            break;
        }
        colon++;
        while (*colon == ' ' || *colon == '\t') {
            colon++;
        }
        if (*colon != '"') {
            p += 3;
            continue;
        }
        colon++;
        size_t i = 0;
        while (*colon && *colon != '"' && i + 1 < SHIP_MAX_ID) {
            rows[n].key[i++] = *colon++;
        }
        rows[n].key[i] = '\0';
        const char *vp = strstr(colon, "\"v\"");
        if (!vp) {
            break;
        }
        const char *vc = strchr(vp, ':');
        if (!vc) {
            break;
        }
        rows[n].val = atof(vc + 1);
        n++;
        p = colon;
    }
    free(raw);
    *n_rows = n;
    return 0;
}

static int cmp_lines(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

int stage_emit(const MetricRow *rows, int n_rows, char *body, size_t body_len) {
    char *lines[SHIP_MAX_ROWS];
    char storage[SHIP_MAX_ROWS][SHIP_MAX_LINE];
    for (int i = 0; i < n_rows; i++) {
        fmt_lane(rows[i].key, rows[i].val, 6, storage[i], sizeof(storage[i]));
        size_t L = strlen(storage[i]);
        if (L + 1 < sizeof(storage[i])) {
            storage[i][L] = '\n';
            storage[i][L + 1] = '\0';
        }
        lines[i] = storage[i];
    }
    qsort(lines, (size_t)n_rows, sizeof(char *), cmp_lines);
    size_t used = 0;
    body[0] = '\0';
    for (int i = 0; i < n_rows; i++) {
        size_t L = strlen(lines[i]);
        if (used + L + 1 >= body_len) {
            return -1;
        }
        memcpy(body + used, lines[i], L);
        used += L;
        body[used] = '\0';
    }
    return 0;
}
