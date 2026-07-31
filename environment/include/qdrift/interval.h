#ifndef QDRIFT_INTERVAL_H
#define QDRIFT_INTERVAL_H

typedef struct {
    double lo;
    double hi;
} qdrift_interval_t;

double qdrift_interval_drift(const qdrift_interval_t *ref, const qdrift_interval_t *quant);

#endif
