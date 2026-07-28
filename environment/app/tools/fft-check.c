#include "orbit_fft.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static int run_case(int width, int height) {
    const int sw = width / 2 + 1, bins = 6;
    const size_t n = (size_t)height * (size_t)sw;
    double *power = calloc(n, sizeof(double));
    double *sums = calloc((size_t)bins, sizeof(double));
    uint64_t *counts = calloc((size_t)bins, sizeof(uint64_t));
    if (!power || !sums || !counts) { free(power); free(sums); free(counts); return 2; }
    for (size_t i = 0; i < n; ++i) power[i] = (double)(i + 1U);
    int rc = orbit_radial_accumulate(power, width, height, sw, sums, counts, bins);
    uint64_t assigned = 0; for (int i = 0; i < bins; ++i) assigned += counts[i];
    printf("%dx%d assigned=%llu\n", width, height, (unsigned long long)assigned);
    free(power); free(sums); free(counts); return rc;
}
int main(void) { if (run_case(47, 47) != 0) return 3; if (run_case(48, 48) != 0) return 4; return 0; }
