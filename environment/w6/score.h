#ifndef SCORE_H
#define SCORE_H
#include "perc.h"
double score_margin(const struct model *m, const struct example *ex);
int score_predict(const struct model *m, const struct example *ex);
void score_digest(const struct model *m, char out[16]);
void score_fence(const struct model *m, char out[16]);
#endif
