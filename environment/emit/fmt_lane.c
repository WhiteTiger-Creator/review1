#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void fmt_lane(const char *key, double val, int scale, char *out, size_t out_len) {
    char num[96];
    snprintf(num, sizeof(num), "%.*f", scale, val);
    const char *lc = getenv("LC_ALL");
    const char *ln = getenv("LC_NUMERIC");
    int german = 0;
    if (lc && strstr(lc, "de_DE")) {
        german = 1;
    }
    if (ln && strstr(ln, "de_DE")) {
        german = 1;
    }
    if (german) {
        for (char *p = num; *p; p++) {
            if (*p == '.') {
                *p = ',';
            }
        }
    }
    snprintf(out, out_len, "%s=%s", key, num);
}

void fmt_lane_legacy(const char *key, double val, char *out, size_t out_len) {
    snprintf(out, out_len, "%s~%.3f", key, val);
}
