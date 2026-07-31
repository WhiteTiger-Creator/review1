#include "qdrift/interval.h"

#include <math.h>

double qdrift_interval_drift(const qdrift_interval_t *ref, const qdrift_interval_t *quant) {
    double d1 = fabs(ref->lo - quant->lo);
    double d2 = fabs(ref->hi - quant->hi);
    return d1 > d2 ? d1 : d2;
}
