#ifndef OPS_H
#define OPS_H
#include "perc.h"
int desk_init(struct desk *d);
int emit_ledger(const struct desk *d);
int op_cycle(struct desk *d, const char *suite_path);
int op_load_cases(struct desk *d, const char *cases_path);
#endif
