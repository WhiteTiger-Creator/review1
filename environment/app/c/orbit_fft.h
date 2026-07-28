#ifndef ORBIT_FFT_H
#define ORBIT_FFT_H
#include <stddef.h>
#include <stdint.h>
int orbit_fftw_power(const double *input, int width, int height, double *power, size_t power_length);
int orbit_radial_accumulate(const double *power, int width, int height, int spectrum_width, double *sums, uint64_t *counts, int bin_count);
const char *orbit_fftw_runtime_version(void);
#endif
