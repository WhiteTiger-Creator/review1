#include "ops.h"
#include "page.h"
#include "score.h"
#include <string.h>
int op_page_dispatch(struct desk *d, const char *op) {
	if (strcmp(op, "publish") == 0) {
		page_publish(d);
		if (d->nruns < MAX_RUNS) {
			struct run_row *r = &d->runs[d->nruns++];
			memset(r, 0, sizeof(*r));
			snprintf(r->action, sizeof(r->action), "publish");
			snprintf(r->outcome, sizeof(r->outcome), "ok");
			r->epoch = d->m.generation;
			r->persist_id = d->m.persist_id;
			score_digest(&d->m, r->digest);
			score_fence(&d->m, r->fence);
			snprintf(r->notes, sizeof(r->notes), "dual_slot");
		}
		return 0;
	}
	if (strcmp(op, "tear") == 0) {
		page_tear(d);
		if (d->nruns < MAX_RUNS) {
			struct run_row *r = &d->runs[d->nruns++];
			memset(r, 0, sizeof(*r));
			snprintf(r->action, sizeof(r->action), "tear");
			snprintf(r->outcome, sizeof(r->outcome), "ok");
			r->persist_id = d->m.persist_id;
			snprintf(r->notes, sizeof(r->notes), "partial_set");
		}
		return 0;
	}
	if (strcmp(op, "recover") == 0) return page_recover(d);
	return 1;
}
