#ifndef SHIP_TYPES_H
#define SHIP_TYPES_H

#include <stddef.h>

#define SHIP_MAX_ID 64
#define SHIP_MAX_PATH 512
#define SHIP_MAX_CANDS 32
#define SHIP_MAX_ROWS 64
#define SHIP_MAX_LINE 256
#define SHIP_MAX_NOTE 256
#define SHIP_SHA_HEX 65
#define SHIP_PREFIX 12
#define SHIP_MAX_PACK 16

typedef struct {
    char id[SHIP_MAX_ID];
    char path[SHIP_MAX_PATH];
    int tier;
    double mtime;
} SnapRef;

typedef struct {
    char id[SHIP_MAX_ID];
    int tier;
    char supersedes[SHIP_MAX_CANDS][SHIP_MAX_ID];
    int n_super;
} BookEntry;

typedef struct {
    BookEntry entries[SHIP_MAX_CANDS];
    int n_entries;
} LedgerView;

typedef struct {
    char key[SHIP_MAX_ID];
    double val;
} MetricRow;

typedef struct {
    char selected_id[SHIP_MAX_ID];
    char book_stamp[SHIP_SHA_HEX];
    char pack_label[SHIP_MAX_PACK];
    char stage_path[SHIP_MAX_PATH];
    int complete; /* 1 when promote finished */
    int generation;
} JournalState;

#endif
