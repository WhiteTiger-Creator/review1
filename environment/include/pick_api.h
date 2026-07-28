#ifndef PICK_API_H
#define PICK_API_H

#include "ship_types.h"

int book_load(const char *path, LedgerView *view);
int book_stamp(const char *path, char *out_hex, size_t out_len);
int scan_snaps(const char *snaps_root, const LedgerView *view, SnapRef *out, int *n_out);
void rank_list(const SnapRef *cands, int n, char *buf, size_t buf_len);
SnapRef rank_pick(const SnapRef *cands, int n, const LedgerView *view);

#endif
