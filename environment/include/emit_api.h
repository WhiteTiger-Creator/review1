#ifndef EMIT_API_H
#define EMIT_API_H

#include "ship_types.h"

int load_metrics(const char *tree_path, MetricRow *rows, int *n_rows);
void fmt_lane(const char *key, double val, int scale, char *out, size_t out_len);
void fmt_lane_legacy(const char *key, double val, char *out, size_t out_len);
int stage_emit(const MetricRow *rows, int n_rows, char *body, size_t body_len);
const char *pack_label_from_env(void);

#endif
