#include "ship_api.h"

#include <stdio.h>
#include <string.h>

void rank_list(const SnapRef *cands, int n, char *buf, size_t buf_len) {
    size_t used = 0;
    buf[0] = '\0';
    for (int i = 0; i < n; i++) {
        char line[SHIP_MAX_LINE];
        snprintf(line, sizeof(line), "%s tier=%d mtime=%.0f\n", cands[i].id, cands[i].tier,
                 cands[i].mtime);
        size_t L = strlen(line);
        if (used + L + 1 >= buf_len) {
            break;
        }
        memcpy(buf + used, line, L);
        used += L;
        buf[used] = '\0';
    }
}
