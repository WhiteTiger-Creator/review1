#include "fnv.h"
#include <stdint.h>
#include <stdio.h>
void fnv32_hex(const char *s, char out[16]) {
	uint32_t h = 2166136261u;
	const unsigned char *p = (const unsigned char *)s;
	while (*p) { h ^= *p++; h *= 16777619u; }
	snprintf(out, 16, "%08x", h);
}
