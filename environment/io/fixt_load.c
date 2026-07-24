#include "fixt_load.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int read_array(const char *key, const char *text, double *out, int max_n) {
    const char *p = strstr(text, key);
    if (!p) {
        return -1;
    }
    p = strchr(p, '[');
    if (!p) {
        return -1;
    }
    p++;
    int count = 0;
    while (*p && *p != ']' && count < max_n) {
        while (*p == ' ' || *p == ',') {
            p++;
        }
        if (*p == ']') {
            break;
        }
        out[count++] = strtod(p, (char **)&p);
    }
    return count;
}

static double read_scalar(const char *key, const char *text, double fallback) {
    const char *p = strstr(text, key);
    if (!p) {
        return fallback;
    }
    p = strchr(p, ':');
    if (!p) {
        return fallback;
    }
    p++;
    return strtod(p, NULL);
}

int fixt_load_json(const char *path, struct model_spec *spec) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return -1;
    }
    fseek(fp, 0, SEEK_END);
    long sz = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    if (sz <= 0 || sz > 65536) {
        fclose(fp);
        return -1;
    }
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(fp);
        return -1;
    }
    if (fread(buf, 1, (size_t)sz, fp) != (size_t)sz) {
        free(buf);
        fclose(fp);
        return -1;
    }
    buf[sz] = '\0';
    fclose(fp);

    memset(spec, 0, sizeof(*spec));
    spec->n = (int)read_scalar("\"n\"", buf, 4.0);
    spec->shift = read_scalar("\"shift\"", buf, 0.0);
    spec->dt_large = read_scalar("\"dt_large\"", buf, 0.30);
    spec->dt_step = read_scalar("\"dt_step\"", buf, 0.015);
    read_array("\"diag\"", buf, spec->diag, Q7_MAX_N);
    read_array("\"off\"", buf, spec->off, Q7_MAX_N - 1);
    int fine_n = read_array("\"dt_fine\"", buf, spec->dt_fine, 2);
    if (fine_n < 2) {
        spec->dt_fine[0] = 0.005;
        spec->dt_fine[1] = 0.01;
    }
    const char *name = strstr(buf, "\"name\"");
    if (name) {
        name = strchr(name, ':');
        if (name) {
            name = strchr(name, '"');
            if (name) {
                name++;
                snprintf(spec->name, sizeof(spec->name), "%.31s", name);
                char *end = strchr(spec->name, '"');
                if (end) {
                    *end = '\0';
                }
            }
        }
    }
    free(buf);
    return 0;
}
