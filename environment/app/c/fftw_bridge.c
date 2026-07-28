#include "orbit_fft.h"
#include <fftw3.h>
#include <stddef.h>
#include <string.h>
int orbit_fftw_power(const double *input, int width, int height, double *power, size_t power_length) {
    if (input == NULL || power == NULL || width < 4 || height < 4) return 1;
    const int spectrum_width = width / 2 + 1;
    const size_t input_count = (size_t)width * (size_t)height;
    const size_t output_count = (size_t)height * (size_t)spectrum_width;
    if (power_length != output_count) return 2;
    double *work = fftw_alloc_real(input_count);
    fftw_complex *frequency = fftw_alloc_complex(output_count);
    if (work == NULL || frequency == NULL) { fftw_free(work); fftw_free(frequency); return 3; }
    memcpy(work, input, input_count * sizeof(double));
    fftw_plan plan = fftw_plan_dft_r2c_2d(height, width, work, frequency, FFTW_ESTIMATE);
    if (plan == NULL) { fftw_free(work); fftw_free(frequency); return 4; }
    fftw_execute(plan);
    for (size_t i = 0; i < output_count; ++i) {
        const double re = frequency[i][0], im = frequency[i][1];
        power[i] = re * re + im * im;
    }
    fftw_destroy_plan(plan); fftw_free(work); fftw_free(frequency); return 0;
}
const char *orbit_fftw_runtime_version(void) { return fftw_version; }
