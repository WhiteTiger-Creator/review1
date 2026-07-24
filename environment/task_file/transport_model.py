"""Public forward model for multicarrier Hall transport calibration."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ELEMENTARY_CHARGE_C = 1.602176634e-19
BOLTZMANN_MEV_K = 0.08617333262145
FINDINGS = [
    "excluded_observation",
    "prior_flag",
    "longitudinal_outlier",
    "hall_outlier",
    "run_bias",
]
ROUNDING = {
    "carrier_parameters": 6,
    "run_parameters": 6,
    "modeled_uohm_m": 6,
    "residual_sigma": 6,
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_archive(input_dir: str | Path) -> dict:
    """Load a compatible transport archive into typed dictionaries."""
    root = Path(input_dir)
    cfg = {row["key"]: float(row["value"]) for row in _rows(root / "case_config.csv")}
    cfg["output_decimals"] = int(cfg["output_decimals"])
    carriers = [
        {
            "carrier_id": row["carrier_id"],
            "band_index": int(row["band_index"]),
            "charge_sign": int(row["charge_sign"]),
            "density_min_1e22_m3": float(row["density_min_1e22_m3"]),
            "density_max_1e22_m3": float(row["density_max_1e22_m3"]),
            "prior_density_1e22_m3": float(row["prior_density_1e22_m3"]),
            "mobility_min_cm2_vs": float(row["mobility_min_cm2_vs"]),
            "mobility_max_cm2_vs": float(row["mobility_max_cm2_vs"]),
            "prior_mobility_cm2_vs": float(row["prior_mobility_cm2_vs"]),
            "activation_min_mev": float(row["activation_min_mev"]),
            "activation_max_mev": float(row["activation_max_mev"]),
            "prior_activation_mev": float(row["prior_activation_mev"]),
            "alpha_min": float(row["alpha_min"]),
            "alpha_max": float(row["alpha_max"]),
            "prior_alpha": float(row["prior_alpha"]),
        }
        for row in _rows(root / "carriers.csv")
    ]
    runs = [
        {
            "run_id": row["run_id"],
            "temperature_k": float(row["temperature_k"]),
            "field_scale_min": float(row["field_scale_min"]),
            "field_scale_max": float(row["field_scale_max"]),
            "prior_field_scale": float(row["prior_field_scale"]),
            "longitudinal_offset_min_uohm_m": float(
                row["longitudinal_offset_min_uohm_m"]
            ),
            "longitudinal_offset_max_uohm_m": float(
                row["longitudinal_offset_max_uohm_m"]
            ),
            "prior_longitudinal_offset_uohm_m": float(
                row["prior_longitudinal_offset_uohm_m"]
            ),
            "hall_offset_min_uohm_m": float(row["hall_offset_min_uohm_m"]),
            "hall_offset_max_uohm_m": float(row["hall_offset_max_uohm_m"]),
            "prior_hall_offset_uohm_m": float(row["prior_hall_offset_uohm_m"]),
        }
        for row in _rows(root / "runs.csv")
    ]
    observations = [
        {
            "observation_id": int(row["observation_id"]),
            "run_id": row["run_id"],
            "field_t": float(row["field_t"]),
            "observed_longitudinal_uohm_m": float(
                row["observed_longitudinal_uohm_m"]
            ),
            "observed_hall_uohm_m": float(row["observed_hall_uohm_m"]),
            "sigma_longitudinal_uohm_m": float(
                row["sigma_longitudinal_uohm_m"]
            ),
            "sigma_hall_uohm_m": float(row["sigma_hall_uohm_m"]),
            "use_flag": int(row["use_flag"]),
        }
        for row in _rows(root / "observations.csv")
    ]
    prior_flags = {
        int(row["observation_id"]) for row in _rows(root / "prior_flags.csv")
    }
    return {
        "cfg": cfg,
        "carriers": carriers,
        "runs": runs,
        "observations": observations,
        "prior_flags": prior_flags,
    }


def modeled_pair(
    archive: dict,
    carrier_parameters: dict[str, dict[str, float]],
    run_parameters: dict[str, dict[str, float]],
    observation: dict,
) -> tuple[float, float]:
    """Evaluate the documented conductivity tensor for one observation."""
    run = next(row for row in archive["runs"] if row["run_id"] == observation["run_id"])
    temperature = run["temperature_k"]
    reference_temperature = archive["cfg"]["reference_temperature_k"]
    field = observation["field_t"] * run_parameters[run["run_id"]]["field_scale"]
    sigma_xx = 0.0
    sigma_xy = 0.0
    for carrier in archive["carriers"]:
        values = carrier_parameters[carrier["carrier_id"]]
        density = values["density_1e22_m3"] * 1.0e22 * math.exp(
            -(values["activation_mev"] / BOLTZMANN_MEV_K)
            * (1.0 / temperature - 1.0 / reference_temperature)
        )
        mobility = (
            values["mobility_cm2_vs"]
            * 1.0e-4
            * (temperature / reference_temperature) ** (-values["alpha"])
        )
        denominator = 1.0 + (mobility * field) ** 2
        sigma_xx += density * mobility / denominator
        sigma_xy += (
            carrier["charge_sign"]
            * density
            * mobility
            * mobility
            * field
            / denominator
        )
    sigma_xx *= ELEMENTARY_CHARGE_C
    sigma_xy *= ELEMENTARY_CHARGE_C
    denominator = sigma_xx * sigma_xx + sigma_xy * sigma_xy
    parameters = run_parameters[run["run_id"]]
    longitudinal = (
        1.0e6 * sigma_xx / denominator
        + parameters["longitudinal_offset_uohm_m"]
    )
    hall = -1.0e6 * sigma_xy / denominator + parameters["hall_offset_uohm_m"]
    return longitudinal, hall


def nearest_rank_p90(values: list[float]) -> float:
    """Return nearest-rank p90, or zero for no values."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)] if ordered else 0.0


def read_parameters(output_dir: str | Path) -> tuple[dict, dict]:
    """Read canonical emitted parameters."""
    with (Path(output_dir) / "transport_parameters.json").open() as handle:
        payload = json.load(handle)
    carriers = {
        row["carrier_id"]: {
            "density_1e22_m3": float(row["density_1e22_m3"]),
            "mobility_cm2_vs": float(row["mobility_cm2_vs"]),
            "activation_mev": float(row["activation_mev"]),
            "alpha": float(row["alpha"]),
        }
        for row in payload["carriers"]
    }
    runs = {
        row["run_id"]: {
            "field_scale": float(row["field_scale"]),
            "longitudinal_offset_uohm_m": float(
                row["longitudinal_offset_uohm_m"]
            ),
            "hall_offset_uohm_m": float(row["hall_offset_uohm_m"]),
        }
        for row in payload["runs"]
    }
    return carriers, runs


def constraint_metrics(
    archive: dict, carrier_parameters: dict, run_parameters: dict
) -> dict[str, float]:
    """Recompute every documented final-state physical metric."""
    densities = [
        carrier_parameters[row["carrier_id"]]["density_1e22_m3"]
        for row in archive["carriers"]
    ]
    mobilities = [
        carrier_parameters[row["carrier_id"]]["mobility_cm2_vs"]
        for row in archive["carriers"]
    ]
    activations = [
        carrier_parameters[row["carrier_id"]]["activation_mev"]
        for row in archive["carriers"]
    ]
    total_density = sum(densities)
    signed_density = sum(
        row["charge_sign"] * density
        for row, density in zip(archive["carriers"], densities, strict=True)
    )
    contributions = [
        density * mobility
        for density, mobility in zip(densities, mobilities, strict=True)
    ]
    total_contribution = sum(contributions)
    shares = [value / total_contribution for value in contributions]
    mobility_ratios = [
        left / right for left, right in zip(mobilities, mobilities[1:], strict=False)
    ]
    activation_steps = [
        abs(left - right)
        for left, right in zip(activations, activations[1:], strict=False)
    ]
    field_scales = [
        run_parameters[row["run_id"]]["field_scale"] for row in archive["runs"]
    ]
    field_steps = [
        abs(left - right)
        for left, right in zip(field_scales, field_scales[1:], strict=False)
    ]
    longitudinal_offsets = [
        run_parameters[row["run_id"]]["longitudinal_offset_uohm_m"]
        for row in archive["runs"]
    ]
    hall_offsets = [
        run_parameters[row["run_id"]]["hall_offset_uohm_m"]
        for row in archive["runs"]
    ]
    return {
        "charge_imbalance": abs(signed_density) / total_density,
        "total_density_1e22_m3": total_density,
        "minimum_conductivity_share": min(shares),
        "minimum_mobility_ratio": min(mobility_ratios) if mobility_ratios else 0.0,
        "maximum_activation_step_mev": max(activation_steps, default=0.0),
        "maximum_field_scale_step": max(field_steps, default=0.0),
        "mean_longitudinal_offset_uohm_m": sum(longitudinal_offsets)
        / len(longitudinal_offsets),
        "mean_hall_offset_uohm_m": sum(hall_offsets) / len(hall_offsets),
    }


def evaluate(input_dir: str | Path, output_dir: str | Path) -> dict:
    """Replay emitted parameters and compute residual metrics and findings."""
    archive = load_archive(input_dir)
    carriers, runs = read_parameters(output_dir)
    modeled = [
        modeled_pair(archive, carriers, runs, row) for row in archive["observations"]
    ]
    residuals = [
        (
            (pair[0] - row["observed_longitudinal_uohm_m"])
            / row["sigma_longitudinal_uohm_m"],
            (pair[1] - row["observed_hall_uohm_m"]) / row["sigma_hall_uohm_m"],
        )
        for pair, row in zip(modeled, archive["observations"], strict=True)
    ]
    eligible = [
        row["use_flag"] != 0 and row["observation_id"] not in archive["prior_flags"]
        for row in archive["observations"]
    ]
    magnitudes = [math.hypot(left, right) / math.sqrt(2.0) for left, right in residuals]
    run_medians = {}
    for run in archive["runs"]:
        values = sorted(
            magnitude
            for magnitude, row, use in zip(
                magnitudes, archive["observations"], eligible, strict=True
            )
            if use and row["run_id"] == run["run_id"]
        )
        middle = len(values) // 2
        run_medians[run["run_id"]] = (
            0.0
            if not values
            else values[middle]
            if len(values) % 2
            else 0.5 * (values[middle - 1] + values[middle])
        )
    findings = []
    scored_longitudinal = []
    scored_hall = []
    scored_magnitude = []
    clean = 0
    threshold = archive["cfg"]["residual_sigma_threshold"]
    bias_threshold = archive["cfg"]["run_bias_sigma_threshold"]
    for residual, magnitude, row, use in zip(
        residuals, magnitudes, archive["observations"], eligible, strict=True
    ):
        current = []
        if row["use_flag"] == 0:
            current.append("excluded_observation")
        if row["observation_id"] in archive["prior_flags"]:
            current.append("prior_flag")
        if use:
            scored_longitudinal.append(residual[0])
            scored_hall.append(residual[1])
            scored_magnitude.append(magnitude)
            if abs(residual[0]) > threshold:
                current.append("longitudinal_outlier")
            if abs(residual[1]) > threshold:
                current.append("hall_outlier")
            if abs(magnitude - run_medians[row["run_id"]]) > bias_threshold:
                current.append("run_bias")
            clean += not current
        findings.append(current)
    count = len(scored_longitudinal)
    longitudinal_rms = (
        math.sqrt(sum(value * value for value in scored_longitudinal) / count)
        if count
        else 0.0
    )
    hall_rms = (
        math.sqrt(sum(value * value for value in scored_hall) / count)
        if count
        else 0.0
    )
    combined_rms = math.sqrt(
        (longitudinal_rms * longitudinal_rms + hall_rms * hall_rms) / 2.0
    )
    return {
        "modeled": modeled,
        "residuals": residuals,
        "findings": findings,
        "scored": count,
        "clean": clean,
        "combined_rms": combined_rms,
        "longitudinal_rms": longitudinal_rms,
        "hall_rms": hall_rms,
        "residual_p90": nearest_rank_p90(scored_magnitude),
        "clean_fraction": clean / count if count else 1.0,
        "finding_counts": {
            name: sum(name in row for row in findings) for name in FINDINGS
        },
    }
