#ifndef JOURNAL_API_H
#define JOURNAL_API_H

#include "ship_types.h"

int journal_load(const char *out_dir, JournalState *st);
int journal_begin(const char *out_dir, const char *selected_id, const char *book_hex,
                  const char *pack_label, int generation, JournalState *st);
int journal_write_stage(JournalState *st, const char *body);
int journal_promote(JournalState *st, const char *out_dir, const char *digest_hex);
int journal_recover(const char *out_dir, JournalState *st);
int sha256_hex_of(const char *data, size_t len, char *out_hex, size_t out_len);

#endif
