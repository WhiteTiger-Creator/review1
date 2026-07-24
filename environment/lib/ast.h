#ifndef Q7_AST_H
#define Q7_AST_H

#include <stddef.h>

enum ast_kind {
    AST_MUL = 1,
    AST_DIV = 2,
    AST_LEAF = 3,
};

struct ast_node {
    enum ast_kind kind;
    double leaf;
    struct ast_node *left;
    struct ast_node *right;
};

struct emit_ctx {
    int profile_id;
    char buf[128];
    size_t len;
};

void ast_init_mul(struct ast_node *n, double a, double b, double c);
double ast_eval(const struct ast_node *n);

#endif
