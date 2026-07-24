#ifndef LEDGER_H
#define LEDGER_H

#include "common.h"

int ledger_write_json(const char *path, struct trace_row *rows, int count);

#endif
