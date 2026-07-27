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

static const char *find_key(const char *p, const char *key) {
    char pat[96];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    return strstr(p, pat);
}

static int parse_string_after(const char *p, char *out, size_t out_len) {
    const char *c = strchr(p, ':');
    if (!c) {
        return -1;
    }
    c++;
    while (*c == ' ' || *c == '\t') {
        c++;
    }
    if (*c != '"') {
        return -1;
    }
    c++;
    size_t i = 0;
    while (*c && *c != '"' && i + 1 < out_len) {
        out[i++] = *c++;
    }
    out[i] = '\0';
    return 0;
}

static int parse_int_after(const char *p, int *out) {
    const char *c = strchr(p, ':');
    if (!c) {
        return -1;
    }
    *out = atoi(c + 1);
    return 0;
}

int book_load(const char *path, LedgerView *view) {
    size_t len = 0;
    char *raw = read_file(path, &len);
    if (!raw) {
        return -1;
    }
    memset(view, 0, sizeof(*view));
    const char *p = raw;
    while ((p = find_key(p, "id")) != NULL && view->n_entries < SHIP_MAX_CANDS) {
        BookEntry *e = &view->entries[view->n_entries];
        memset(e, 0, sizeof(*e));
        if (parse_string_after(p, e->id, sizeof(e->id)) != 0) {
            p += 2;
            continue;
        }
        const char *tier_p = find_key(p, "evidence_tier");
        if (tier_p && tier_p < p + 200) {
            parse_int_after(tier_p, &e->tier);
        }
        const char *sup = find_key(p, "supersedes");
        if (sup && sup < p + 400) {
            const char *br = strchr(sup, '[');
            const char *er = br ? strchr(br, ']') : NULL;
            if (br && er) {
                const char *q = br;
                while ((q = strchr(q, '"')) != NULL && q < er && e->n_super < SHIP_MAX_CANDS) {
                    q++;
                    size_t i = 0;
                    while (*q && *q != '"' && i + 1 < SHIP_MAX_ID) {
                        e->supersedes[e->n_super][i++] = *q++;
                    }
                    e->supersedes[e->n_super][i] = '\0';
                    if (i > 0) {
                        e->n_super++;
                    }
                    if (*q == '"') {
                        q++;
                    }
                }
            }
        }
        view->n_entries++;
        p += 3;
    }
    free(raw);
    return 0;
}

int book_stamp(const char *path, char *out_hex, size_t out_len) {
    size_t len = 0;
    char *raw = read_file(path, &len);
    if (!raw) {
        return -1;
    }
    int rc = sha256_hex_of(raw, len, out_hex, out_len);
    free(raw);
    return rc;
}
