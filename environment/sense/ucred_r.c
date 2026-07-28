#include "ucred_r.h"

int read_pair(const struct ucred_pair *pair, int32_t *pinned, int32_t *current) {
    if (pair == 0 || pinned == 0 || current == 0) {
        return -1;
    }
    *pinned = pair->pinned_uid;
    *current = pair->current_uid;
    return 0;
}

int skew(const struct ucred_pair *pair) {
    int32_t pinned = 0;
    int32_t current = 0;
    if (read_pair(pair, &pinned, &current) != 0) {
        return 0;
    }
    return (int)(current - pinned);
}
