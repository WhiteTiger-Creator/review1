#ifndef QDRIFT_WITNESS_SEAL_H
#define QDRIFT_WITNESS_SEAL_H

#include "qdrift/propagate_engine.h"

int qdrift_write_walk_witness(const char *staging_dir, const qdrift_snapshot_t *snap);
int qdrift_validate_walk_witness(const char *staging_dir, const qdrift_snapshot_t *snap);
int qdrift_bump_publish_ledger(const char *graph_id, const char *witness_hex);

#endif
