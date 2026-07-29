#include "ops.h"
#include <stdio.h>
#include <sys/stat.h>
int emit_ledger(const struct desk *d) {
	mkdir("/app/output", 0755);
	FILE *f = fopen(LEDGER_PATH, "w");
	if (!f) return -1;
	fprintf(f, "{\n  \"schema\": \"perc_model_v1\",\n");
	fprintf(f, "  \"journal_path\": \"%s\",\n", ACTIVE_PAGE);
	fprintf(f, "  \"journal_generation\": %llu,\n", (unsigned long long)d->m.generation);
	fprintf(f, "  \"deny_count\": %d,\n", d->deny_count);
	fprintf(f, "  \"updates\": %llu,\n", (unsigned long long)d->m.updates);
	fprintf(f, "  \"runs\": [\n");
	for (int i = 0; i < d->nruns; i++) {
		const struct run_row *r = &d->runs[i];
		fprintf(f, "    {\"action\":\"%s\",\"case_id\":\"%s\",\"outcome\":\"%s\",\"reason\":\"%s\",",
			r->action, r->case_id, r->outcome, r->reason);
		fprintf(f, "\"epoch\":%llu,\"pred\":%d,\"label\":%d,\"margin\":%.6f,",
			(unsigned long long)r->epoch, r->pred, r->label, r->margin);
		fprintf(f, "\"digest\":\"%s\",\"fence\":\"%s\",\"persist_id\":%llu,",
			r->digest, r->fence, (unsigned long long)r->persist_id);
		fprintf(f, "\"carried\":%d,\"lineage_skew\":%d,\"notes\":\"%s\"}%s\n",
			r->carried, r->lineage_skew, r->notes, (i+1<d->nruns)?",":"");
	}
	fprintf(f, "  ]\n}\n");
	fclose(f);
	return 0;
}
