#ifndef ARCHIVE_API_H
#define ARCHIVE_API_H

#include "ship_types.h"

int memo_pack(const char *case_id, const char *selected_id, const char *note_text,
              const char *sha_prefix, const char *pack_label, const char *archive_root);
int memo_scan(const char *archive_root);

#endif
