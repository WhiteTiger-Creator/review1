#include "step.h"
#include "score.h"
#include <string.h>

static int feat_index(struct model *m, const char *name) {
	for (int i = 0; i < m->nfeats; i++) {
		if (m->feats[i].active && strcmp(m->feats[i].name, name) == 0) return i;
	}
	return -1;
}

int step_train_one(struct model *m, const struct example *ex) {
	double margin = score_margin(m, ex);
	(void)margin;
	m->updates += 1;
	for (int i = 0; i < ex->nfeats; i++) {
		int idx = feat_index(m, ex->feats[i]);
		if (idx < 0) continue;
		m->w[idx] += (double)ex->label;
		m->u[idx] += m->w[idx];
	}
	m->bias += (double)ex->label;
	m->ubias += m->bias;
	return 1;
}
