from __future__ import annotations


def wtac_decoy_pitot_blend(q_rho_v: float, pitot_q: float, mix: float = 0.5) -> float:
    """Non-authoritative blend of density-velocity q with uncorrected pitot. Do not use for eval."""
    m = max(0.0, min(1.0, float(mix)))
    return (1.0 - m) * float(q_rho_v) + m * float(pitot_q)
