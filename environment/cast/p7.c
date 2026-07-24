#include "p7.h"

#include <stdio.h>

int p7_format_suffix(char *out, size_t cap, double v, const char *suffix) {
    if (!out || cap == 0 || !suffix) {
        return -1;
    }
    return snprintf(out, cap, "%.6g%s", v, suffix) >= 0 ? 0 : -1;
}
