package analysis

/*
#cgo CFLAGS: -I${SRCDIR}/../../c
#cgo LDFLAGS: -L${SRCDIR}/../../build -lorbitfft -lfftw3 -lm
#include "orbit_fft.h"
*/
import "C"

import (
	"fmt"
	"strings"
	"unsafe"
)

func fftPower(input []float64, width, height int) ([]float64, error) {
	if width < 4 || height < 4 || len(input) != width*height {
		return nil, fmt.Errorf("invalid FFT dimensions")
	}
	spectrumWidth := width/2 + 1
	power := make([]float64, height*spectrumWidth)
	rc := C.orbit_fftw_power((*C.double)(unsafe.Pointer(&input[0])), C.int(width), C.int(height), (*C.double)(unsafe.Pointer(&power[0])), C.size_t(len(power)))
	if rc != 0 {
		return nil, fmt.Errorf("FFTW bridge failed: %d", int(rc))
	}
	return power, nil
}

func FFTWVersion() (string, error) {
	raw := C.GoString(C.orbit_fftw_runtime_version())
	marker := "fftw-"
	start := strings.Index(raw, marker)
	if start < 0 {
		return "", fmt.Errorf("unrecognized FFTW version %q", raw)
	}
	version := raw[start+len(marker):]
	if cut := strings.IndexByte(version, '-'); cut >= 0 {
		version = version[:cut]
	}
	return version, nil
}

func radial(power []float64, width, height, bins int) ([]float64, error) {
	sw := width/2 + 1
	if len(power) != height*sw || bins < 1 {
		return nil, fmt.Errorf("invalid radial dimensions")
	}
	sums := make([]float64, bins)
	counts := make([]uint64, bins)
	rc := C.orbit_radial_accumulate((*C.double)(unsafe.Pointer(&power[0])), C.int(width), C.int(height), C.int(sw), (*C.double)(unsafe.Pointer(&sums[0])), (*C.uint64_t)(unsafe.Pointer(&counts[0])), C.int(bins))
	if rc != 0 {
		return nil, fmt.Errorf("radial helper failed: %d", int(rc))
	}
	values := make([]float64, bins)
	for index := range values {
		if counts[index] == 0 {
			return nil, fmt.Errorf("empty radial bin %d", index+1)
		}
		values[index] = sums[index] / float64(counts[index])
	}
	return values, nil
}
