#include <stdio.h>
#include <string.h>
void decoy_note(char *dst, size_t n) { if (dst && n) snprintf(dst, n, "%s", "metrics"); }
