#include "ops.h"
#include "fold.h"
#include <stdio.h>
#include <string.h>
int op_fold(struct desk *d) {
	if (fold_manifest(d, MANIFEST_PATH) != 0) return -1;
	if (d->nruns < MAX_RUNS) {
		struct run_row *r = &d->runs[d->nruns++];
		memset(r, 0, sizeof(*r));
		snprintf(r->action, sizeof(r->action), "fold");
		snprintf(r->outcome, sizeof(r->outcome), "ok");
		r->epoch = d->m.generation;
		r->persist_id = d->m.persist_id;
		snprintf(r->notes, sizeof(r->notes), "feats:%d", d->m.nfeats);
	}
	return 0;
}
