#include "perc.h"
int decoy_idle(const struct desk *d) { return d ? (int)d->m.persist_id : 0; }
