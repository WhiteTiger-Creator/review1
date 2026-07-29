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
	if (read_page(ACTIVE_PAGE, &d->m) != 0) read_page(STANDBY_PAGE, &d->m);
	unlink(PARTIAL_MARK);
	if (d->nruns < MAX_RUNS) {
		struct run_row *r = &d->runs[d->nruns++];
		memset(r, 0, sizeof(*r));
		snprintf(r->action, sizeof(r->action), "recover");
		snprintf(r->outcome, sizeof(r->outcome), "ok");
		r->epoch = d->m.generation;
		r->persist_id = d->m.persist_id;
		r->lineage_skew = (had && d->m.generation == 0) ? 1 : 0;
		snprintf(r->notes, sizeof(r->notes), "%s", had ? "ignored_partial" : "clean");
	}
	return 0;
}

int page_load_model(struct desk *d) {
	return read_page(ACTIVE_PAGE, &d->m);
}
