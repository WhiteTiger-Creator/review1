#ifndef QDRIFT_BOUND_COMPARE_H
#define QDRIFT_BOUND_COMPARE_H

#include "qdrift/propagate_engine.h"

typedef struct {
    char layer_id[QDRIFT_MAX_ID_LEN];
    double measured_drift;
    double bound;
} qdrift_violation_t;

typedef struct {
    char graph_id[64];
    char variant_id[64];
    char scenario_id[64];
    double drift_bound;
    int certified;
    qdrift_violation_t violations[QDRIFT_MAX_LAYERS];
    int violation_count;
} qdrift_cert_report_t;

int qdrift_build_cert_report(
    const qdrift_snapshot_t *snap,
    const qdrift_scenario_t *scenario,
    int certification_epoch,
    qdrift_cert_report_t *report
);

#endif
