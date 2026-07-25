"""Independent compatible-archive builder used by the verifier."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

E_CHARGE = 1.602176634e-19
KB_MEV_K = 0.08617333262145


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _forward(
    carriers: list[dict], run: dict, field_t: float, reference_temperature: float
) -> tuple[float, float]:
    temperature = run["temperature"]
    field = field_t * run["scale"]
    sigma_xx = 0.0
    sigma_xy = 0.0
    for row in carriers:
        density = row["density"] * 1.0e22 * math.exp(
            -(row["activation"] / KB_MEV_K)
            * (1.0 / temperature - 1.0 / reference_temperature)
        )
        mobility = (
            row["mobility"]
            * 1.0e-4
            * (temperature / reference_temperature) ** (-row["alpha"])
        )
        denominator = 1.0 + (mobility * field) ** 2
        sigma_xx += density * mobility / denominator
        sigma_xy += (
            row["sign"]
            * density
            * mobility
            * mobility
            * field
            / denominator
        )
    sigma_xx *= E_CHARGE
    sigma_xy *= E_CHARGE
    denominator = sigma_xx * sigma_xx + sigma_xy * sigma_xy
    return (
        1.0e6 * sigma_xx / denominator + run["long_offset"],
        -1.0e6 * sigma_xy / denominator + run["hall_offset"],
    )


def make_case(mode: int, root: Path) -> None:
    """Build a deterministic regime with changed scientific dimensions."""
    root.mkdir(parents=True, exist_ok=True)
    carrier_count = 2 + mode % 3
    run_count = 6 + mode % 3
    reference_temperature = 300.0 + 2.0 * math.sin(0.37 * mode)
    signs = [-1, 1, -1, 1]
    if carrier_count == 2:
        densities = [4.82 + 0.04 * math.sin(mode), 5.08 + 0.04 * math.sin(mode)]
    elif carrier_count == 3:
        first = 3.05 + 0.05 * math.sin(0.71 * mode)
        third = 2.08 + 0.04 * math.cos(0.43 * mode)
        densities = [
            first,
            first + third + 0.18 * math.sin(0.29 * mode),
            third,
        ]
    else:
        densities = [
            3.36 + 0.04 * math.sin(mode),
            2.91 + 0.03 * math.cos(mode),
            2.02 + 0.03 * math.sin(0.5 * mode),
            2.60 + 0.03 * math.cos(0.5 * mode),
        ]
    mobility_base = [824.0, 432.0, 224.0, 116.0]
    activation_base = [18.0, 25.0, 32.0, 39.0]
    alpha_base = [1.12, 1.34, 1.57, 1.79]
    carriers = []
    carrier_rows = []
    for index in range(carrier_count):
        density = densities[index]
        mobility = mobility_base[index] * (
            1.0 + 0.018 * math.sin(mode + index)
        )
        activation = activation_base[index] + 0.28 * math.sin(
            0.47 * mode + index
        )
        alpha = alpha_base[index] + 0.025 * math.cos(0.31 * mode + index)
        carrier = {
            "id": f"B{index + 1}",
            "sign": signs[index],
            "density": density,
            "mobility": mobility,
            "activation": activation,
            "alpha": alpha,
        }
        carriers.append(carrier)
        carrier_rows.append(
            {
                "carrier_id": carrier["id"],
                "band_index": index + 1,
                "charge_sign": signs[index],
                "density_min_1e22_m3": f"{density * 0.72:.6f}",
                "density_max_1e22_m3": f"{density * 1.28:.6f}",
                "prior_density_1e22_m3": f"{density * (1.15 if (index + mode) % 2 == 0 else 0.87):.6f}",
                "mobility_min_cm2_vs": f"{mobility * 0.68:.6f}",
                "mobility_max_cm2_vs": f"{mobility * 1.32:.6f}",
                "prior_mobility_cm2_vs": f"{mobility * (0.88 if (index + mode) % 2 == 0 else 1.11):.6f}",
                "activation_min_mev": f"{activation - 8.0:.6f}",
                "activation_max_mev": f"{activation + 8.0:.6f}",
                "prior_activation_mev": f"{activation + (3.6 if (index + mode) % 2 == 0 else -3.3):.6f}",
                "alpha_min": f"{max(0.2, alpha - 0.55):.6f}",
                "alpha_max": f"{alpha + 0.55:.6f}",
                "prior_alpha": f"{alpha + (-0.22 if (index + mode) % 2 == 0 else 0.20):.6f}",
            }
        )

    temperatures = [
        228.0 + 26.0 * index + 1.7 * math.sin(mode + index)
        for index in range(run_count)
    ]
    long_offsets = [
        3.4 * math.sin(0.81 * index + 0.23 * mode)
        for index in range(run_count)
    ]
    hall_offsets = [
        2.8 * math.cos(0.67 * index + 0.19 * mode)
        for index in range(run_count)
    ]
    long_mean = sum(long_offsets) / run_count
    hall_mean = sum(hall_offsets) / run_count
    long_offsets = [value - long_mean for value in long_offsets]
    hall_offsets = [value - hall_mean for value in hall_offsets]
    runs = []
    run_rows = []
    for index, temperature in enumerate(temperatures):
        scale = 1.0 + 0.0024 * math.sin(0.55 * index + 0.13 * mode)
        run = {
            "id": f"R{index + 1}",
            "temperature": temperature,
            "scale": scale,
            "long_offset": long_offsets[index],
            "hall_offset": hall_offsets[index],
        }
        runs.append(run)
        run_rows.append(
            {
                "run_id": run["id"],
                "temperature_k": f"{temperature:.6f}",
                "field_scale_min": f"{scale - 0.025:.6f}",
                "field_scale_max": f"{scale + 0.025:.6f}",
                "prior_field_scale": f"{scale + (0.014 if (index + mode) % 2 else -0.013):.6f}",
                "longitudinal_offset_min_uohm_m": f"{long_offsets[index] - 14.0:.6f}",
                "longitudinal_offset_max_uohm_m": f"{long_offsets[index] + 14.0:.6f}",
                "prior_longitudinal_offset_uohm_m": f"{long_offsets[index] + (6.0 if index % 2 else -5.5):.6f}",
                "hall_offset_min_uohm_m": f"{hall_offsets[index] - 12.0:.6f}",
                "hall_offset_max_uohm_m": f"{hall_offsets[index] + 12.0:.6f}",
                "prior_hall_offset_uohm_m": f"{hall_offsets[index] + (-5.2 if index % 2 else 5.6):.6f}",
            }
        )

    fields = [-3.0, -2.1, -1.35, -0.7, 0.0, 0.7, 1.35, 2.1, 3.0]
    if mode in {4, 9, 14}:
        fields = [-3.2, -2.4, -1.2, -0.35, 0.0, 0.35, 1.2, 2.4, 3.2]
    observations = []
    for run in runs:
        for field_t in fields:
            longitudinal, hall = _forward(
                carriers, run, field_t, reference_temperature
            )
            observation_id = len(observations) + 1
            sigma_long = 1.3 + 0.0007 * abs(longitudinal)
            sigma_hall = 1.1 + 0.0010 * abs(hall)
            observations.append(
                {
                    "observation_id": observation_id,
                    "run_id": run["id"],
                    "field_t": f"{field_t:.6f}",
                    "observed_longitudinal_uohm_m": f"{longitudinal + 0.065 * math.sin(1.19 * observation_id + 0.31 * mode) * sigma_long:.6f}",
                    "observed_hall_uohm_m": f"{hall + 0.070 * math.cos(1.07 * observation_id + 0.27 * mode) * sigma_hall:.6f}",
                    "sigma_longitudinal_uohm_m": f"{sigma_long:.6f}",
                    "sigma_hall_uohm_m": f"{sigma_hall:.6f}",
                    "use_flag": 1,
                }
            )
    excluded = (11 * mode + 7) % len(observations)
    flagged = (17 * mode + 23) % len(observations)
    if flagged == excluded:
        flagged = (flagged + 5) % len(observations)
    observations[excluded]["use_flag"] = 0
    observations[excluded]["observed_hall_uohm_m"] = (
        f"{float(observations[excluded]['observed_hall_uohm_m']) + 8.0 * float(observations[excluded]['sigma_hall_uohm_m']):.6f}"
    )
    observations[flagged]["observed_longitudinal_uohm_m"] = (
        f"{float(observations[flagged]['observed_longitudinal_uohm_m']) - 7.0 * float(observations[flagged]['sigma_longitudinal_uohm_m']):.6f}"
    )
    diagnostic = (29 * mode + 31) % len(observations)
    while diagnostic in {excluded, flagged}:
        diagnostic = (diagnostic + 1) % len(observations)
    observations[diagnostic]["observed_longitudinal_uohm_m"] = (
        f"{float(observations[diagnostic]['observed_longitudinal_uohm_m']) + 2.52 * float(observations[diagnostic]['sigma_longitudinal_uohm_m']):.6f}"
    )
    total_density = sum(densities)
    signed_density = abs(
        sum(signs[index] * densities[index] for index in range(carrier_count))
    )
    contributions = [
        densities[index]
        * mobility_base[index]
        * (1.0 + 0.018 * math.sin(mode + index))
        for index in range(carrier_count)
    ]
    minimum_share = min(contributions) / sum(contributions)
    four = carrier_count == 4
    config = {
        "residual_sigma_threshold": 2.30,
        "run_bias_sigma_threshold": 2.05,
        "combined_rms_max": 0.55 if four else 0.34,
        "longitudinal_rms_max": 0.75 if four else 0.46,
        "hall_rms_max": 0.45 if four else 0.20,
        "residual_p90_max": 0.85 if four else 0.34,
        "min_clean_fraction": 0.975,
        "reference_temperature_k": reference_temperature,
        "max_charge_imbalance": signed_density / total_density
        + (0.040 if four else 0.020),
        "total_density_min_1e22_m3": total_density - (0.34 if four else 0.22),
        "total_density_max_1e22_m3": total_density + (0.34 if four else 0.22),
        "min_conductivity_share": minimum_share - (0.022 if four else 0.014),
        "min_mobility_ratio": 1.64 if four else 1.72,
        "max_activation_step_mev": 10.0 if four else 7.60,
        "max_field_scale_step": 0.010 if four else 0.006,
        "max_mean_longitudinal_offset_uohm_m": 0.50 if four else 0.35,
        "max_mean_hall_offset_uohm_m": 0.50 if four else 0.35,
        "output_decimals": 6,
    }
    _write(
        root / "case_config.csv",
        ["key", "value"],
        [{"key": key, "value": f"{value:.12f}"} for key, value in config.items()],
    )
    _write(
        root / "carriers.csv",
        [
            "carrier_id",
            "band_index",
            "charge_sign",
            "density_min_1e22_m3",
            "density_max_1e22_m3",
            "prior_density_1e22_m3",
            "mobility_min_cm2_vs",
            "mobility_max_cm2_vs",
            "prior_mobility_cm2_vs",
            "activation_min_mev",
            "activation_max_mev",
            "prior_activation_mev",
            "alpha_min",
            "alpha_max",
            "prior_alpha",
        ],
        carrier_rows,
    )
    _write(
        root / "runs.csv",
        [
            "run_id",
            "temperature_k",
            "field_scale_min",
            "field_scale_max",
            "prior_field_scale",
            "longitudinal_offset_min_uohm_m",
            "longitudinal_offset_max_uohm_m",
            "prior_longitudinal_offset_uohm_m",
            "hall_offset_min_uohm_m",
            "hall_offset_max_uohm_m",
            "prior_hall_offset_uohm_m",
        ],
        run_rows,
    )
    if mode in {8, 15}:
        observations = observations[::2] + observations[1::2]
    _write(
        root / "observations.csv",
        [
            "observation_id",
            "run_id",
            "field_t",
            "observed_longitudinal_uohm_m",
            "observed_hall_uohm_m",
            "sigma_longitudinal_uohm_m",
            "sigma_hall_uohm_m",
            "use_flag",
        ],
        observations,
    )
    _write(
        root / "prior_flags.csv",
        ["observation_id", "reason"],
        [{"observation_id": flagged + 1, "reason": "contact_settling"}],
    )
    names = [
        "case_config.csv",
        "carriers.csv",
        "runs.csv",
        "observations.csv",
        "prior_flags.csv",
    ]
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in names
    }
    (root / "input_hashes.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n"
    )
