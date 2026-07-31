from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import subprocess
from pathlib import Path

import jsonschema
import pytest

APP = Path("/app")
CONFIG = APP / "data" / "lattice_config.json"
OBS = APP / "data" / "observations.json"
VALID = APP / "data" / "validation_cases.json"
SCORING = APP / "data" / "scoring_cases.json"
SCHEMA = APP / "api" / "calibration.schema.json"
COMMAND = APP / "bin" / "lattice-calibrate"
OUT = APP / "out" / "calibration.json"
TSV = APP / "out" / "current_model.tsv"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _validate_levels(rows: list[dict], severity: list[str], recency: list[str]) -> None:
    for row in rows:
        assert row["severity"] in severity
        assert row["recency"] in recency


def _rate(block: dict, alpha: float) -> float:
    denom = block["trials"] + 2.0 * alpha * len(block["cells"])
    if denom == 0:
        return 0.5
    return (block["events"] + alpha * len(block["cells"])) / denom


def _fit_surface(
    severity: list[str],
    recency: list[str],
    observations: list[dict],
    alpha: float,
) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], float]]:
    cells = {(sev, rec): {"events": 0, "trials": 0} for sev in severity for rec in recency}
    for row in observations:
        cells[(row["severity"], row["recency"])]["events"] += row["events"]
        cells[(row["severity"], row["recency"])]["trials"] += row["trials"]

    block_for: dict[tuple[str, str], dict] = {}
    blocks: list[dict] = []
    for key, counts in cells.items():
        block = {"cells": [key], "events": counts["events"], "trials": counts["trials"]}
        blocks.append(block)
        block_for[key] = block

    sev_index = {value: idx for idx, value in enumerate(severity)}
    rec_index = {value: idx for idx, value in enumerate(recency)}
    changed = True
    while changed:
        changed = False
        for si, sev in enumerate(severity):
            for ri, rec in enumerate(recency):
                neighbors = []
                if si + 1 < len(severity):
                    neighbors.append((severity[si + 1], rec))
                if ri + 1 < len(recency):
                    neighbors.append((sev, recency[ri + 1]))
                for neighbor in neighbors:
                    left = block_for[(sev, rec)]
                    right = block_for[neighbor]
                    if left is right or _rate(left, alpha) <= _rate(right, alpha):
                        continue
                    merged = {
                        "cells": sorted(
                            left["cells"] + right["cells"],
                            key=lambda cell: (sev_index[cell[0]], rec_index[cell[1]]),
                        ),
                        "events": left["events"] + right["events"],
                        "trials": left["trials"] + right["trials"],
                    }
                    for cell in merged["cells"]:
                        block_for[cell] = merged
                    blocks = [block for block in blocks if block is not left and block is not right]
                    blocks.append(merged)
                    changed = True
    probabilities = {key: _rate(block_for[key], alpha) for key in cells}
    return cells, probabilities


def _nll(probabilities: dict[tuple[str, str], float], validation: list[dict]) -> float:
    total = 0.0
    for row in validation:
        p = min(max(probabilities[(row["severity"], row["recency"])], 1e-15), 1.0 - 1e-15)
        label = row["label"]
        weight = float(row.get("weight", 1))
        total += weight * -(label * math.log(p) + (1 - label) * math.log(1.0 - p))
    return total


def _clip(probability: float) -> float:
    return min(max(probability, 1e-15), 1.0 - 1e-15)


def _logit(probability: float) -> float:
    safe = _clip(probability)
    return math.log(safe / (1.0 - safe))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _shrink_surface(
    probabilities: dict[tuple[str, str], float],
    observations: list[dict],
    alpha: float,
    shrinkage: float,
) -> dict[tuple[str, str], float]:
    total_events = sum(row["events"] for row in observations)
    total_trials = sum(row["trials"] for row in observations)
    denom = total_trials + 2.0 * alpha
    base = 0.5 if denom == 0 else (total_events + alpha) / denom
    base_logit = _logit(base)
    return {
        key: _sigmoid((1.0 - shrinkage) * _logit(probability) + shrinkage * base_logit)
        for key, probability in probabilities.items()
    }


def _fit_calibrator(probabilities: dict[tuple[str, str], float], validation: list[dict]) -> list[dict]:
    blocks = []
    for row in sorted(validation, key=lambda item: (probabilities[(item["severity"], item["recency"])], item["case_id"])):
        raw = probabilities[(row["severity"], row["recency"])]
        weight = float(row.get("weight", 1))
        blocks.append(
            {
                "min_raw": raw,
                "max_raw": raw,
                "weight": weight,
                "weighted_events": weight * row["label"],
            }
        )
    index = 0
    while index < len(blocks) - 1:
        current_rate = blocks[index]["weighted_events"] / blocks[index]["weight"]
        next_rate = blocks[index + 1]["weighted_events"] / blocks[index + 1]["weight"]
        if current_rate > next_rate:
            merged = {
                "min_raw": min(blocks[index]["min_raw"], blocks[index + 1]["min_raw"]),
                "max_raw": max(blocks[index]["max_raw"], blocks[index + 1]["max_raw"]),
                "weight": blocks[index]["weight"] + blocks[index + 1]["weight"],
                "weighted_events": blocks[index]["weighted_events"] + blocks[index + 1]["weighted_events"],
            }
            blocks[index : index + 2] = [merged]
            index = max(index - 1, 0)
        else:
            index += 1
    return blocks


def _calibrate_probability(probability: float, blocks: list[dict]) -> float:
    if not blocks:
        return probability
    for block in blocks:
        if probability <= block["max_raw"]:
            return block["weighted_events"] / block["weight"]
    return blocks[-1]["weighted_events"] / blocks[-1]["weight"]


def _calibrate_surface(probabilities: dict[tuple[str, str], float], blocks: list[dict]) -> dict[tuple[str, str], float]:
    return {key: _calibrate_probability(probability, blocks) for key, probability in probabilities.items()}


def _decision(probability: float, thresholds: dict) -> str:
    if probability >= float(thresholds["alert"]):
        return "alert"
    if probability >= float(thresholds["monitor"]):
        return "monitor"
    return "clear"


def _expected() -> dict:
    config = _load(CONFIG)
    observations = _load(OBS)
    validation = _load(VALID)
    scoring = _load(SCORING)
    severity = config["severity"]
    recency = config["recency"]
    _validate_levels(observations, severity, recency)
    _validate_levels(validation, severity, recency)
    _validate_levels(scoring, severity, recency)

    fits = []
    for alpha_value in config["candidate_alpha"]:
        alpha = float(alpha_value)
        _cells, probabilities = _fit_surface(severity, recency, observations, alpha)
        for shrinkage_value in config["candidate_shrinkage"]:
            shrinkage = float(shrinkage_value)
            shrunk = _shrink_surface(probabilities, observations, alpha, shrinkage)
            blocks = _fit_calibrator(shrunk, validation)
            calibrated = _calibrate_surface(shrunk, blocks)
            fits.append(
                {
                    "alpha": alpha,
                    "shrinkage": shrinkage,
                    "probabilities": calibrated,
                    "calibration_blocks": blocks,
                    "raw_validation_nll": _nll(shrunk, validation),
                    "calibrated_validation_nll": _nll(calibrated, validation),
                }
            )
    best = min(fits, key=lambda fit: (fit["calibrated_validation_nll"], fit["alpha"], fit["shrinkage"]))
    cells, pooled = _fit_surface(severity, recency, observations, best["alpha"])
    shrunk = _shrink_surface(pooled, observations, best["alpha"], best["shrinkage"])
    probabilities = _calibrate_surface(shrunk, best["calibration_blocks"])
    thresholds = config["decision_thresholds"]
    input_sha = hashlib.sha256(b"".join(path.read_bytes() for path in [CONFIG, OBS, VALID, SCORING])).hexdigest()
    return {
        "schema_version": "monotone-lattice/v1",
        "generated_at": "2026-07-28T00:00:00Z",
        "selected_alpha": round(best["alpha"], 6),
        "selected_shrinkage": round(best["shrinkage"], 6),
        "validation_nll": round(best["calibrated_validation_nll"], 6),
        "levels": {"severity": severity, "recency": recency},
        "candidate_scores": [
            {
                "alpha": round(fit["alpha"], 6),
                "shrinkage": round(fit["shrinkage"], 6),
                "raw_validation_nll": round(fit["raw_validation_nll"], 6),
                "calibrated_validation_nll": round(fit["calibrated_validation_nll"], 6),
            }
            for fit in sorted(fits, key=lambda fit: (fit["alpha"], fit["shrinkage"]))
        ],
        "calibration_blocks": [
            {
                "min_raw_probability": round(block["min_raw"], 6),
                "max_raw_probability": round(block["max_raw"], 6),
                "calibrated_probability": round(block["weighted_events"] / block["weight"], 6),
                "weight": round(block["weight"], 6),
            }
            for block in best["calibration_blocks"]
        ],
        "cells": [
            {
                "severity": sev,
                "recency": rec,
                "events": cells[(sev, rec)]["events"],
                "trials": cells[(sev, rec)]["trials"],
                "probability": round(probabilities[(sev, rec)], 6),
            }
            for sev in severity
            for rec in recency
        ],
        "scoring": [
            {
                "case_id": row["case_id"],
                "severity": row["severity"],
                "recency": row["recency"],
                "probability": round(probabilities[(row["severity"], row["recency"])], 6),
                "decision": _decision(round(probabilities[(row["severity"], row["recency"])], 6), thresholds),
            }
            for row in sorted(scoring, key=lambda item: item["case_id"])
        ],
        "input_sha256": input_sha,
    }


@pytest.fixture(scope="session")
def result() -> dict:
    """Run the submitted calibrator after verifier-only data changes that static answers cannot know."""
    config = _load(CONFIG)
    config["candidate_shrinkage"] = [0, 0.2, 0.45, 0.7]
    _write(CONFIG, config)
    observations = _load(OBS)
    observations.extend(
        [
            {"severity": "guarded", "recency": "fresh", "events": 8, "trials": 14},
            {"severity": "critical", "recency": "warm", "events": 7, "trials": 9},
        ]
    )
    _write(OBS, observations)
    validation = _load(VALID)
    validation.extend(
        [
            {"case_id": "v-dynamic-a", "severity": "guarded", "recency": "fresh", "label": 1, "weight": 1.7},
            {"case_id": "v-dynamic-b", "severity": "critical", "recency": "warm", "label": 1, "weight": 1.3},
        ]
    )
    _write(VALID, validation)
    scoring = _load(SCORING)
    scoring.append({"case_id": "s-verifier", "severity": "guarded", "recency": "fresh"})
    _write(SCORING, scoring)

    (APP / "out").mkdir(exist_ok=True)
    OUT.write_text('{"stale": true}\n', encoding="utf-8")
    TSV.write_text("stale\tmodel\n", encoding="utf-8")
    assert COMMAND.exists(), "missing /app/bin/lattice-calibrate"
    completed = subprocess.run(
        [str(COMMAND)],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert OUT.exists(), "calibration JSON was not written"
    assert TSV.exists(), "current model TSV was not written"
    return json.loads(OUT.read_text(encoding="utf-8"))


def test_json_schema_and_exact_report(result: dict) -> None:
    """The report validates against the visible schema and matches an independent implementation."""
    jsonschema.validate(result, _load(SCHEMA))
    assert result == _expected()


def test_monotone_surface_and_dynamic_scoring_case(result: dict) -> None:
    """The fitted lattice is monotone in both configured dimensions and includes verifier-added scoring."""
    config = _load(CONFIG)
    probs = {(cell["severity"], cell["recency"]): cell["probability"] for cell in result["cells"]}
    for si, sev in enumerate(config["severity"]):
        for ri, rec in enumerate(config["recency"]):
            if si + 1 < len(config["severity"]):
                assert probs[(sev, rec)] <= probs[(config["severity"][si + 1], rec)]
            if ri + 1 < len(config["recency"]):
                assert probs[(sev, rec)] <= probs[(sev, config["recency"][ri + 1])]
    scoring_ids = [item["case_id"] for item in result["scoring"]]
    assert scoring_ids == sorted(scoring_ids)
    assert "s-verifier" in scoring_ids


def test_candidate_selection_uses_unrounded_validation_nll(result: dict) -> None:
    """The chosen smoothing/shrinkage pair follows validation NLL with documented tie-breaks."""
    config = _load(CONFIG)
    scores = result["candidate_scores"]
    assert len(scores) == len(config["candidate_alpha"]) * len(config["candidate_shrinkage"])
    assert scores == sorted(scores, key=lambda row: (row["alpha"], row["shrinkage"]))
    assert any(row["shrinkage"] == 0.7 for row in scores)
    best = min(scores, key=lambda row: (row["calibrated_validation_nll"], row["alpha"], row["shrinkage"]))
    assert result["selected_alpha"] == best["alpha"]
    assert result["selected_shrinkage"] == best["shrinkage"]
    assert result["validation_nll"] == best["calibrated_validation_nll"]


def test_selected_isotonic_calibration_blocks_are_used(result: dict) -> None:
    """The selected second-stage calibrator is monotone and changes the final lattice probabilities."""
    blocks = result["calibration_blocks"]
    assert len(blocks) >= 2
    assert blocks == sorted(blocks, key=lambda row: (row["min_raw_probability"], row["max_raw_probability"]))
    for left, right in itertools.pairwise(blocks):
        assert left["max_raw_probability"] <= right["max_raw_probability"]
        assert left["calibrated_probability"] <= right["calibrated_probability"]
    expected = _expected()
    assert result["calibration_blocks"] == expected["calibration_blocks"]


def test_tsv_matches_sorted_cells_and_cell_decisions(result: dict) -> None:
    """The TSV current model is sorted by lattice order and uses cell-level rounded probabilities."""
    config = _load(CONFIG)
    lines = TSV.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "severity\trecency\tprobability\tdecision"
    expected_lines = ["severity\trecency\tprobability\tdecision"]
    for cell in result["cells"]:
        expected_lines.append(
            "\t".join(
                [
                    cell["severity"],
                    cell["recency"],
                    f"{cell['probability']:.6f}",
                    _decision(cell["probability"], config["decision_thresholds"]),
                ]
            )
        )
    assert lines == expected_lines


def test_rerun_replaces_outputs_for_changed_live_data(result: dict) -> None:
    """A later valid input change recomputes the current artifacts and removes stale bytes."""
    before = copy.deepcopy(result)
    original_observations = OBS.read_text(encoding="utf-8")
    try:
        OUT.write_text(json.dumps(before, sort_keys=True, indent=2) + "\nSTALE\n", encoding="utf-8")
        observations = _load(OBS)
        observations.append({"severity": "high", "recency": "fresh", "events": 6, "trials": 7})
        _write(OBS, observations)
        completed = subprocess.run([str(COMMAND)], cwd=APP, text=True, capture_output=True, timeout=60, check=False)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        after = json.loads(OUT.read_text(encoding="utf-8"))
        assert after == _expected()
        assert after["input_sha256"] != before["input_sha256"]
        assert "STALE" not in OUT.read_text(encoding="utf-8")
    finally:
        OBS.write_text(original_observations, encoding="utf-8")
        completed = subprocess.run([str(COMMAND)], cwd=APP, text=True, capture_output=True, timeout=60, check=False)
        assert completed.returncode == 0, completed.stderr + completed.stdout


def test_invalid_data_preserves_last_good_outputs(result: dict) -> None:
    """Invalid live data fails without clobbering the most recent successful model files."""
    original_observations = OBS.read_text(encoding="utf-8")
    last_good_json = OUT.read_text(encoding="utf-8")
    last_good_tsv = TSV.read_text(encoding="utf-8")
    try:
        observations = _load(OBS)
        observations.append({"severity": "critical", "recency": "fresh", "events": 12, "trials": 4})
        _write(OBS, observations)
        completed = subprocess.run([str(COMMAND)], cwd=APP, text=True, capture_output=True, timeout=60, check=False)
        assert completed.returncode != 0
        assert OUT.read_text(encoding="utf-8") == last_good_json
        assert TSV.read_text(encoding="utf-8") == last_good_tsv
    finally:
        OBS.write_text(original_observations, encoding="utf-8")
