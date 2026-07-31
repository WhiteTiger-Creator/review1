#ifndef QDRIFT_STAGING_IO_H
#define QDRIFT_STAGING_IO_H

#include "qdrift/propagate_engine.h"

int qdrift_write_pack_context(
    const char *staging_dir,
    const char *graph_id,
    const char *variant_id,
    const char *scenario_id,
    int certification_epoch
);
int qdrift_write_snapshot(const char *staging_dir, const qdrift_snapshot_t *snap);
int qdrift_read_snapshot(const char *staging_dir, qdrift_snapshot_t *snap);

#endif
