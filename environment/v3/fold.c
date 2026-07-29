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

static int cmp_path(const void *a, const void *b) {
	return strcmp(*(const char *const *)a, *(const char *const *)b);
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
	qsort(paths, (size_t)np, sizeof(paths[0]), cmp_path);
	for (int i = 0; i < np; i++) {
		char full[512];
		if (paths[i][0] == '/') snprintf(full, sizeof(full), "%s", paths[i]);
		else snprintf(full, sizeof(full), "/app/environment/%s", paths[i]);
		load_pack(&d->m, full);
		free(paths[i]);
	}
	free(buf);
	return 0;
}
