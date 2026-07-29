#include "ops.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int op_fold(struct desk *d);
extern int op_train_case(struct desk *d, const char *case_id);
extern int op_predict_case(struct desk *d, const char *case_id);
extern int op_page_dispatch(struct desk *d, const char *op);
extern int op_cut(struct desk *d);

static char *slurp(const char *path) {
	FILE *f = fopen(path, "r");
	if (!f) return NULL;
	char *buf=NULL; size_t cap=0,n=0; int c;
	while ((c=fgetc(f))!=EOF){ if(n+1>=cap){cap=cap?cap*2:4096;buf=realloc(buf,cap);} buf[n++]=(char)c; }
	fclose(f); if(buf) buf[n]=0; return buf;
}

static void json_get_str(const char *obj, const char *key, char *out, size_t out_sz) {
	out[0]=0; char pat[64]; snprintf(pat,sizeof(pat),"\"%s\"",key);
	const char *p=strstr(obj,pat); if(!p) return;
	p=strchr(p,':'); p=strchr(p,'"'); if(!p) return; p++;
	const char *e=strchr(p,'"'); if(!e) return;
	size_t n=(size_t)(e-p); if(n>=out_sz) n=out_sz-1;
	memcpy(out,p,n); out[n]=0;
}

int op_cycle(struct desk *d, const char *suite_path) {
	char *buf = slurp(suite_path);
	if (!buf) return -1;
	char cases_path[256] = "/app/environment/fixtures/cases/examples.json";
	char *cp = strstr(buf, "\"cases\"");
	if (cp) {
		char tmp[256]; json_get_str(cp, "cases", tmp, sizeof(tmp));
		if (tmp[0]) {
			if (tmp[0]=='/') snprintf(cases_path,sizeof(cases_path),"%s",tmp);
			else snprintf(cases_path,sizeof(cases_path),"/app/environment/%s",tmp);
		}
	}
	op_load_cases(d, cases_path);
	char *p = strstr(buf, "\"actions\"");
	if (!p) { free(buf); return -1; }
	p = strchr(p, '['); if (!p) { free(buf); return -1; }
	p++;
	while (*p && *p != ']') {
		while (*p && (*p==' '||*p=='\n'||*p=='\t'||*p==',')) p++;
		if (*p != '{') break;
		char *end = strchr(p, '}'); if (!end) break;
		char save = end[1]; end[1]=0;
		char op[32]={0}; json_get_str(p,"op",op,sizeof(op));
		if (strcmp(op,"fold")==0) op_fold(d);
		else if (strcmp(op,"train")==0) { char id[32]; json_get_str(p,"case",id,sizeof(id)); op_train_case(d,id); }
		else if (strcmp(op,"predict")==0) { char id[32]; json_get_str(p,"case",id,sizeof(id)); op_predict_case(d,id); }
		else if (strcmp(op,"cut")==0) op_cut(d);
		else if (strcmp(op,"publish")==0||strcmp(op,"tear")==0||strcmp(op,"recover")==0) op_page_dispatch(d,op);
		end[1]=save; p=end+1;
	}
	free(buf);
	return emit_ledger(d);
}
