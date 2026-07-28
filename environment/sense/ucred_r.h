#ifndef UCRED_R_H
#define UCRED_R_H

#include <stdint.h>

struct ucred_pair {
    int32_t pinned_uid;
    int32_t current_uid;
};

int read_pair(const struct ucred_pair *pair, int32_t *pinned, int32_t *current);
int skew(const struct ucred_pair *pair);

#endif
