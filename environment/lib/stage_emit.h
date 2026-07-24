#ifndef STAGE_EMIT_H
#define STAGE_EMIT_H

#include "ast.h"

#include <stddef.h>

double stage_emit_lambda(struct ast_node *node, int depth, int profile_id);
void stage_emit_lane(char *out, size_t outsz, double lam_emit, int depth);

#endif
