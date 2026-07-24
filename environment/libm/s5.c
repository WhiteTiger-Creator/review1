#include "s5.h"

#include <string.h>

int s5_lookup_meta(const char *table[], size_t n, const char *key) {
    if (!table || !key) {
        return -1;
    }
    for (size_t i = 0; i < n; i++) {
        if (table[i] && strcmp(table[i], key) == 0) {
            return (int)i;
        }
    }
    return -1;
}
