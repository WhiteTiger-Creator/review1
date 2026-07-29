#include "ops.h"
#include "page.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
	struct desk d;
	desk_init(&d);
	if (argc < 2) { fprintf(stderr, "usage: percctl cycle|resume-probe [suite]\n"); return 2; }
	if (strcmp(argv[1], "cycle") == 0) {
		const char *suite = argc >= 3 ? argv[2] : SUITE_PATH;
		return op_cycle(&d, suite) == 0 ? 0 : 1;
	}
	if (strcmp(argv[1], "resume-probe") == 0) {
		extern int op_load_cases(struct desk *, const char *);
		extern int op_predict_case(struct desk *, const char *);
		if (page_recover(&d) != 0) return 1;
		op_load_cases(&d, "/app/environment/fixtures/cases/examples.json");
		op_predict_case(&d, "e_solo");
		emit_ledger(&d);
		return 0;
	}
	return 2;
}
