from __future__ import annotations

import math


def wtac_decoy_prandtl_q(q_inf: float, mach: float) -> float:
    """Decoy compressibility scaling — must not drive facility validation."""
    beta = math.sqrt(max(1.0e-12, 1.0 - mach * mach))
    return q_inf / beta
