#ifndef QDRIFT_CERT_JSON_H
#define QDRIFT_CERT_JSON_H

#include "qdrift/bound_compare.h"

int qdrift_write_cert_report(const qdrift_cert_report_t *report, const char *path);
void qdrift_report_digest(const qdrift_cert_report_t *report, char *hex_out, int hex_len);

#endif
