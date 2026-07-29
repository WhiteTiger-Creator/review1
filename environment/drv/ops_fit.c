#include "ops.h"
#include "score.h"
#include "step.h"
#include <stdio.h>
#include <string.h>

static void push_predict(struct desk *d, const struct example *ex, const char *action) {
	char dig[16], fen[16];
	int pred = score_predict(&d->m, ex);
	double margin = score_margin(&d->m, ex);
	score_digest(&d->m, dig);
	score_fence(&d->m, fen);
	if (d->nruns >= MAX_RUNS) return;
	struct run_row *r = &d->runs[d->nruns++];
	memset(r, 0, sizeof(*r));
	snprintf(r->action, sizeof(r->action), "%s", action);
	snprintf(r->case_id, sizeof(r->case_id), "%s", ex->id);
	r->pred = pred;
	r->label = ex->label;
	r->margin = margin;
	r->epoch = d->m.generation;
	snprintf(r->digest, sizeof(r->digest), "%s", dig);
	snprintf(r->fence, sizeof(r->fence), "%s", fen);
	r->persist_id = d->m.persist_id;
	if (pred == ex->label) {
		snprintf(r->outcome, sizeof(r->outcome), "ok");
	} else {
		snprintf(r->outcome, sizeof(r->outcome), "deny");
		snprintf(r->reason, sizeof(r->reason), "MISPRED");
		d->deny_count++;
	}
}

int op_train_case(struct desk *d, const char *case_id) {
	const struct example *ex = NULL;
	for (int i = 0; i < d->nex; i++) {
		if (strcmp(d->ex[i].id, case_id) == 0) { ex = &d->ex[i]; break; }
	}
	if (!ex) return -1;
	int updated = step_train_one(&d->m, ex);
	if (d->nruns < MAX_RUNS) {
		struct run_row *r = &d->runs[d->nruns++];
		memset(r, 0, sizeof(*r));
		snprintf(r->action, sizeof(r->action), "train");
		snprintf(r->case_id, sizeof(r->case_id), "%s", case_id);
		snprintf(r->outcome, sizeof(r->outcome), updated ? "ok" : "skip");
		if (!updated) snprintf(r->reason, sizeof(r->reason), "MARGIN_OK");
		r->epoch = d->m.generation;
		r->label = ex->label;
		r->margin = score_margin(&d->m, ex);
		r->persist_id = d->m.persist_id;
		snprintf(r->notes, sizeof(r->notes), "upd:%llu", (unsigned long long)d->m.updates);
	}
	return 0;
}

int op_predict_case(struct desk *d, const char *case_id) {
	const struct example *ex = NULL;
	for (int i = 0; i < d->nex; i++) {
		if (strcmp(d->ex[i].id, case_id) == 0) { ex = &d->ex[i]; break; }
	}
	if (!ex) return -1;
	push_predict(d, ex, "predict");
	return 0;
}
