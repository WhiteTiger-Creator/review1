#include "epoch.h"
#include <stdio.h>
#include <string.h>

int epoch_cut(struct desk *d) {
	d->m.generation += 1;
	if (d->nruns < MAX_RUNS) {
		struct run_row *r = &d->runs[d->nruns++];
		memset(r, 0, sizeof(*r));
		snprintf(r->action, sizeof(r->action), "cut");
		snprintf(r->outcome, sizeof(r->outcome), "ok");
		r->epoch = d->m.generation;
		r->persist_id = d->m.persist_id;
		snprintf(r->notes, sizeof(r->notes), "gen_bump");
	}
	return 0;
}
