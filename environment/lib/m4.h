#ifndef M4_H
#define M4_H

#include "ast.h"

char *wrap_mul(struct ast_node *n, int depth, struct emit_ctx *ctx);
double wrap_mul_eval(struct ast_node *n, int depth, int profile_id);
void wrap_mul_emit_lane(char *out, size_t outsz, double lam_emit, int depth);

#endif
