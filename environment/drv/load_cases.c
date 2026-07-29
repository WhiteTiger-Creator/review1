#include "ops.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *slurp(const char *path) {
	FILE *f = fopen(path, "r");
	if (!f) return NULL;
	char *buf=NULL; size_t cap=0,n=0; int c;
	while ((c=fgetc(f))!=EOF){ if(n+1>=cap){cap=cap?cap*2:4096;buf=realloc(buf,cap);} buf[n++]=(char)c; }
	fclose(f); if(buf) buf[n]=0; return buf;
}

int op_load_cases(struct desk *d, const char *cases_path) {
	char *buf = slurp(cases_path);
	if (!buf) return -1;
	d->nex = 0;
	char *p = buf;
	while ((p = strstr(p, "\"id\"")) != NULL && d->nex < MAX_EX) {
		struct example *ex = &d->ex[d->nex];
		memset(ex, 0, sizeof(*ex));
		char *q = strchr(p, ':'); q = strchr(q, '"'); q++;
		char *e = strchr(q, '"');
		snprintf(ex->id, sizeof(ex->id), "%.*s", (int)(e-q), q);
		char *obj_end = strchr(e, '}');
		if (!obj_end) break;
		char save = *obj_end; *obj_end = 0;
		char *lb = strstr(p, "\"label\"");
		if (lb) { lb = strchr(lb, ':'); ex->label = atoi(lb+1); }
		char *ft = strstr(p, "\"feats\"");
		if (ft) {
			ft = strchr(ft, '['); ft++;
			while (*ft && *ft != ']' && ex->nfeats < MAX_FEATS) {
				while (*ft && (*ft==' '||*ft==','||*ft=='\n'||*ft=='\t')) ft++;
				if (*ft=='"'){ ft++; e=strchr(ft,'"');
					snprintf(ex->feats[ex->nfeats], sizeof(ex->feats[0]), "%.*s", (int)(e-ft), ft);
					ex->nfeats++; ft=e+1;
				} else break;
			}
		}
		*obj_end = save;
		d->nex++;
		p = obj_end + 1;
	}
	free(buf);
	return 0;
}
