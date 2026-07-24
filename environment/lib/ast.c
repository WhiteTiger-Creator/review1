#include "ast.h"

#include <stdio.h>
#include <string.h>

void ast_init_mul(struct ast_node *n, double a, double b, double c) {
    n->kind = AST_MUL;
    n->leaf = c;
    n->left = NULL;
    n->right = NULL;
    (void)a;
    (void)b;
}

double ast_eval(const struct ast_node *n) {
    if (!n) {
        return 0.0;
    }
    if (n->kind == AST_LEAF) {
        return n->leaf;
    }
    return n->leaf;
}
