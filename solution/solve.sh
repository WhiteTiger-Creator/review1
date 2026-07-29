#!/bin/bash
set -euo pipefail
root=/app/environment

cat >"$root/v3/fold.c" <<'EOF'
#include "fold.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void clear_feats(struct model *m) {
	m->nfeats = 0;
	memset(m->feats, 0, sizeof(m->feats));
	memset(m->w, 0, sizeof(m->w));
	memset(m->u, 0, sizeof(m->u));
	m->bias = 0;
	m->ubias = 0;
	m->updates = 0;
}

static int find_feat(struct model *m, const char *name) {
	for (int i = 0; i < m->nfeats; i++) {
		if (strcmp(m->feats[i].name, name) == 0) return i;
	}
	return -1;
}

static void add_feat(struct model *m, const char *name, int active) {
	int i = find_feat(m, name);
	if (i < 0) {
		if (m->nfeats >= MAX_FEATS) return;
		i = m->nfeats++;
		snprintf(m->feats[i].name, sizeof(m->feats[i].name), "%s", name);
		m->w[i] = 0;
		m->u[i] = 0;
	}
	m->feats[i].active = active;
}

static int load_pack(struct model *m, const char *path) {
	FILE *f = fopen(path, "r");
	if (!f) return -1;
	char line[256];
	while (fgets(line, sizeof(line), f)) {
		char name[48];
		int active = 1;
		if (sscanf(line, "%47s %d", name, &active) >= 1) {
			if (name[0] == '#' || name[0] == '\0') continue;
			add_feat(m, name, active);
		}
	}
	fclose(f);
	return 0;
}

int fold_manifest(struct desk *d, const char *manifest_path) {
	FILE *f = fopen(manifest_path, "r");
	if (!f) return -1;
	char *buf = NULL; size_t cap = 0, n = 0; int c;
	while ((c = fgetc(f)) != EOF) {
		if (n + 1 >= cap) { cap = cap ? cap * 2 : 4096; buf = realloc(buf, cap); }
		buf[n++] = (char)c;
	}
	fclose(f);
	if (!buf) return -1;
	buf[n] = 0;
	clear_feats(&d->m);
	d->nincludes = 0;
	d->m.persist_id = BOOT_PERSIST;
	if (d->m.generation == 0) d->m.generation = 1;

	char *paths[16];
	int np = 0;
	char *inc = strstr(buf, "\"packs\"");
	if (!inc) { free(buf); return -1; }
	inc = strchr(inc, '[');
	if (!inc) { free(buf); return -1; }
	inc++;
	while (*inc && *inc != ']' && np < 16) {
		while (*inc && (*inc==' '||*inc==','||*inc=='\n'||*inc=='\t')) inc++;
		if (*inc == '"') {
			inc++;
			char *e = strchr(inc, '"');
			if (!e) break;
			size_t len = (size_t)(e - inc);
			paths[np] = malloc(len + 1);
			memcpy(paths[np], inc, len);
			paths[np][len] = 0;
			snprintf(d->include_order[d->nincludes], sizeof(d->include_order[0]), "%s", paths[np]);
			d->nincludes++;
			np++;
			inc = e + 1;
		} else break;
	}
	for (int i = 0; i < np; i++) {
		char full[512];
		int rc;
		if (paths[i][0] == '/') snprintf(full, sizeof(full), "%s", paths[i]);
		else snprintf(full, sizeof(full), "/app/environment/%s", paths[i]);
		rc = load_pack(&d->m, full);
		free(paths[i]);
		paths[i] = NULL;
		if (rc != 0) {
			for (int j = i + 1; j < np; j++) free(paths[j]);
			free(buf);
			return -1;
		}
	}
	free(buf);
	return 0;
}
EOF

cat >"$root/w6/score.c" <<'EOF'
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

static double avg_w(const struct model *m, int i) {
	if (m->updates == 0) return m->w[i];
	return m->u[i] / (double)m->updates;
}

static double avg_bias(const struct model *m) {
	if (m->updates == 0) return m->bias;
	return m->ubias / (double)m->updates;
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
	double s = avg_bias(m);
	for (int i = 0; i < ex->nfeats; i++) {
		int idx = feat_index(m, ex->feats[i]);
		if (idx >= 0) s += avg_w(m, idx);
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
		n += (size_t)snprintf(buf + n, sizeof(buf) - n, "%s:%.6f,", m->feats[i].name, avg_w(m, i));
	}
	n += (size_t)snprintf(buf + n, sizeof(buf) - n, "b=%.6f", avg_bias(m));
	fnv32_hex(buf, out);
}

void score_fence(const struct model *m, char out[16]) {
	char dig[16];
	char buf[128];
	score_digest(m, dig);
	snprintf(buf, sizeof(buf), "%s|%llu|%llu", dig,
		(unsigned long long)m->generation, (unsigned long long)m->updates);
	fnv32_hex(buf, out);
}
EOF

cat >"$root/x1/step.c" <<'EOF'
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
	if (margin > 0.0) return 0;
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
EOF

cat >"$root/y8/page.c" <<'EOF'
#include "page.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void write_page(const char *path, const struct model *m) {
	FILE *f = fopen(path, "w");
	if (!f) return;
	fprintf(f, "generation %llu\n", (unsigned long long)m->generation);
	fprintf(f, "updates %llu\n", (unsigned long long)m->updates);
	fprintf(f, "persist %llu\n", (unsigned long long)m->persist_id);
	fprintf(f, "bias %.10g\n", m->bias);
	fprintf(f, "ubias %.10g\n", m->ubias);
	fprintf(f, "nfeats %d\n", m->nfeats);
	for (int i = 0; i < m->nfeats; i++) {
		fprintf(f, "F %s %d %.10g %.10g\n", m->feats[i].name, m->feats[i].active, m->w[i], m->u[i]);
	}
	fclose(f);
}

static int read_page(const char *path, struct model *m) {
	FILE *f = fopen(path, "r");
	if (!f) return -1;
	unsigned long long gen=0, upd=0, pers=0;
	int nfeats=0;
	if (fscanf(f, "generation %llu\n", &gen) != 1) { fclose(f); return -1; }
	if (fscanf(f, "updates %llu\n", &upd) != 1) { fclose(f); return -1; }
	if (fscanf(f, "persist %llu\n", &pers) != 1) { fclose(f); return -1; }
	if (fscanf(f, "bias %lf\n", &m->bias) != 1) { fclose(f); return -1; }
	if (fscanf(f, "ubias %lf\n", &m->ubias) != 1) { fclose(f); return -1; }
	if (fscanf(f, "nfeats %d\n", &nfeats) != 1) { fclose(f); return -1; }
	m->generation = gen; m->updates = upd; m->persist_id = pers; m->nfeats = 0;
	for (int i = 0; i < nfeats && i < MAX_FEATS; i++) {
		char name[48]; int active; double w, u;
		if (fscanf(f, "F %47s %d %lf %lf\n", name, &active, &w, &u) != 4) break;
		snprintf(m->feats[m->nfeats].name, sizeof(m->feats[0].name), "%s", name);
		m->feats[m->nfeats].active = active;
		m->w[m->nfeats] = w;
		m->u[m->nfeats] = u;
		m->nfeats++;
	}
	fclose(f);
	return 0;
}

int page_publish(struct desk *d) {
	mkdir(MODEL_DIR, 0755);
	write_page(STANDBY_PAGE, &d->m);
	write_page(ACTIVE_PAGE, &d->m);
	unlink(PARTIAL_MARK);
	return 0;
}

int page_tear(struct desk *d) {
	mkdir(MODEL_DIR, 0755);
	write_page(STANDBY_PAGE, &d->m);
	FILE *f = fopen(ACTIVE_PAGE, "w");
	if (f) { fprintf(f, "generation 0\nupdates 0\npersist 0\nbias 0\nubias 0\nnfeats 0\n"); fclose(f); }
	f = fopen(PARTIAL_MARK, "w");
	if (f) { fputs("torn\n", f); fclose(f); }
	return 0;
}

int page_recover(struct desk *d) {
	int had = access(PARTIAL_MARK, F_OK) == 0;
	int rc = -1;
	if (had) {
		rc = read_page(STANDBY_PAGE, &d->m);
		if (rc == 0) write_page(ACTIVE_PAGE, &d->m);
	} else {
		rc = read_page(ACTIVE_PAGE, &d->m);
		if (rc != 0) rc = read_page(STANDBY_PAGE, &d->m);
	}
	unlink(PARTIAL_MARK);
	if (d->nruns < MAX_RUNS) {
		struct run_row *r = &d->runs[d->nruns++];
		memset(r, 0, sizeof(*r));
		snprintf(r->action, sizeof(r->action), "recover");
		snprintf(r->outcome, sizeof(r->outcome), rc == 0 ? "ok" : "deny");
		r->epoch = d->m.generation;
		r->persist_id = d->m.persist_id;
		r->lineage_skew = 0;
		snprintf(r->notes, sizeof(r->notes), "%s", had ? "had_partial" : "clean");
	}
	return rc;
}

int page_load_model(struct desk *d) {
	return read_page(ACTIVE_PAGE, &d->m);
}
EOF

/bin/bash "$root/ci/rebuild.sh"
