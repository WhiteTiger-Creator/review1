#include "qdrift/bound_compare.h"

#include <stdlib.h>
#include <string.h>

static int cmp_violation(const void *a, const void *b) {
    return strcmp(((const qdrift_violation_t *)a)->layer_id, ((const qdrift_violation_t *)b)->layer_id);
}

int qdrift_build_cert_report(
    const qdrift_snapshot_t *snap,
    const qdrift_scenario_t *scenario,
    int certification_epoch,
    qdrift_cert_report_t *report
) {
    memset(report, 0, sizeof(*report));
    strncpy(report->graph_id, snap->graph_id, sizeof(report->graph_id) - 1);
    strncpy(report->variant_id, snap->variant_id, sizeof(report->variant_id) - 1);
    strncpy(report->scenario_id, snap->scenario_id, sizeof(report->scenario_id) - 1);
    report->drift_bound = scenario->drift_bound;
    report->certified = 1;
    for (int i = 0; i < snap->layer_count; ++i) {
        double drift = qdrift_interval_drift(&snap->layers[i].ref, &snap->layers[i].quant);
        int violates = 0;
        if (certification_epoch == 2) {
            violates = drift >= scenario->drift_bound;
        } else {
            violates = drift > scenario->drift_bound;
        }
        if (violates) {
            qdrift_violation_t *v = &report->violations[report->violation_count++];
            strncpy(v->layer_id, snap->layers[i].layer_id, sizeof(v->layer_id) - 1);
            v->measured_drift = drift;
            v->bound = scenario->drift_bound;
            report->certified = 0;
        }
    }
    if (report->violation_count > 1) {
        qsort(report->violations, (size_t)report->violation_count, sizeof(qdrift_violation_t), cmp_violation);
    }
    return 0;
}
