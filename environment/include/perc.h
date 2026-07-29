#ifndef PERC_H
#define PERC_H

#include <stdint.h>

#define MAX_FEATS 64
#define MAX_EX 128
#define MAX_RUNS 96
#define BOOT_PERSIST 0xA11Eu
#define MODEL_DIR "/app/var/model"
#define ACTIVE_PAGE "/app/var/model/active.page"
#define STANDBY_PAGE "/app/var/model/standby.page"
#define PARTIAL_MARK "/app/var/model/active.page.partial"
#define LEDGER_PATH "/app/output/perc_ledger.json"
#define MANIFEST_PATH "/app/environment/fixtures/manifest.json"
#define SUITE_PATH "/app/environment/fixtures/suite.json"

struct feat {
	char name[48];
	int active;
};

struct example {
	char id[32];
	int label; /* +1 or -1 */
	char feats[MAX_FEATS][48];
	int nfeats;
};

struct model {
	struct feat feats[MAX_FEATS];
	int nfeats;
	double w[MAX_FEATS];
	double u[MAX_FEATS]; /* averaged accumulator */
	double bias;
	double ubias;
	uint64_t updates;
	uint64_t generation;
	uint64_t persist_id;
};

struct run_row {
	char action[24];
	char case_id[32];
	char outcome[16];
	char reason[32];
	uint64_t epoch;
	int pred;
	int label;
	double margin;
	char digest[16];
	char fence[16];
	uint64_t persist_id;
	int carried;
	int lineage_skew;
	char notes[96];
};

struct desk {
	struct model m;
	struct example ex[MAX_EX];
	int nex;
	struct run_row runs[MAX_RUNS];
	int nruns;
	int deny_count;
	char include_order[16][128];
	int nincludes;
};

#endif
