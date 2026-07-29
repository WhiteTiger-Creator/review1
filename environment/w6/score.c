#include "score.h"
#include "fnv.h"
#include <stdio.h>
#include <string.h>

static int feat_index(const struct model *m, const char *name) {
	for (int i = 0; i < m->nfeats; i++) {
		if (m->feats[i].active && strcmp(m->feats[i].name, name) == 0) return i;
	}
	return -1;
}

double score_margin(const struct model *m, const struct example *ex) {
	double s = m->bias;
	for (int i = 0; i < ex->nfeats; i++) {
		int idx = feat_index(m, ex->feats[i]);
		if (idx >= 0) s += m->w[idx];
	}
	return s * (double)ex->label;
}

int score_predict(const struct model *m, const struct example *ex) {
	double s = m->bias;
	for (int i = 0; i < ex->nfeats; i++) {
		int idx = feat_index(m, ex->feats[i]);
		if (idx >= 0) s += m->w[idx];
	}
	return s >= 0.0 ? 1 : -1;
}

void score_digest(const struct model *m, char out[16]) {
	char buf[1024];
	size_t n = 0;
	n += (size_t)snprintf(buf + n, sizeof(buf) - n, "g=%llu|u=%llu|",
		(unsigned long long)m->generation, (unsigned long long)m->updates);
	for (int i = 0; i < m->nfeats; i++) {
		if (!m->feats[i].active) continue;
		n += (size_t)snprintf(buf + n, sizeof(buf) - n, "%s:%.6f,", m->feats[i].name, m->w[i]);
	}
	n += (size_t)snprintf(buf + n, sizeof(buf) - n, "b=%.6f", m->bias);
	fnv32_hex(buf, out);
}

void score_fence(const struct model *m, char out[16]) {
	char dig[16];
	char buf[128];
	score_digest(m, dig);
	snprintf(buf, sizeof(buf), "%s|%llu", dig, (unsigned long long)m->updates);
	fnv32_hex(buf, out);
}
