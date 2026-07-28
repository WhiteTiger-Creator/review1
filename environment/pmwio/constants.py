"""Shared acquisition and calibration constants.

Every value here is fixed by the calibration contract documented under
``docs/overview.md``. Nothing else in the tree may re-declare one of
these names with a different value.
"""

from __future__ import annotations

import math

SCHEMA_VERSION = 2

PMW2_MAGIC = b"PMW2"
PMW2_VERSION = 2
FILE_HEADER_BYTES = 24
FRAME_HEADER_BYTES = 28
VALID_ADC_BITS = (12, 14)
MIN_SAMPLE_COUNT = 64
MAX_SAMPLE_COUNT = 512
KIND_PEDESTAL = 0
KIND_PULSER = 1
VALID_KINDS = (KIND_PEDESTAL, KIND_PULSER)
VALID_POLARITIES = (1, -1)

PRE_TRIGGER = 32
INTEGRATION_HALF_WIDTH = 8
GATE_WIDTH = 2 * INTEGRATION_HALF_WIDTH + 1
MIN_COVERAGE = 0.70
OUTLIER_K = 3.0
MAD_SCALE = 1.4826
MIN_BASELINE_SAMPLES = 8
PILEUP_FRAC = 0.35
PILEUP_SEP = 6

# Variance of a uniform one-LSB quantization error; floors the per-sample noise.
QUANTIZATION_VAR = 1.0 / 12.0
# Asymptotic variance of a median relative to the mean, for Gaussian noise.
MEDIAN_VARIANCE_FACTOR = math.pi / 2.0

PEDESTAL_K = 8
PEDESTAL_P = 4
PEDESTAL_VAR_FLOOR = 1.0
NOISE_SIGMA_LIMIT = 12.0

MIN_OBS = 6
MIN_DISTINCT_LEVELS = 3
COND_THRESHOLD = 1.0e12
COMMON_MODE_SCALE = 0.25

PUBLICATION_DIGITS = 9
