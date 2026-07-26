"""Behaviorally evaluate exposure-corrected item-choice predictions."""

import csv
import hashlib
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from functools import cache
from pathlib import Path

import pytest

FIELDS = ["event_id", "item_id", "probability"]
LANDLOCK = Path("/tests/landlock_exec.py")
PUBLIC_INPUT = Path("/app/data")
RELATIONS = (
    "training_choices.csv",
    "training_candidates.csv",
    "evaluation_choices.csv",
    "evaluation_candidates.csv",
)


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sandbox_command(input_dir, output_dir, command):
    return [
        sys.executable,
        str(LANDLOCK),
        "--read",
        str(input_dir),
        "--write",
        str(output_dir),
        "--",
        *command,
    ]


def run_candidate_artifact(input_dir):
    output = Path(tempfile.mkdtemp(prefix="choice-output-", dir="/dev/shm"))
    output.chmod(0o777)
    prediction_path = output / "choice_predictions.csv"
    prediction_path.write_text("stale,output\nmust,disappear\n", encoding="utf-8")
    prediction_path.chmod(0o666)
    environment = dict(os.environ, HOME=str(output), TMPDIR=str(output))
    result = subprocess.run(
        sandbox_command(
            input_dir,
            output,
            ["/app/run.sh", str(input_dir), str(output)],
        ),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        cwd="/app",
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert prediction_path.is_file() and prediction_path.stat().st_size > 0
    return read_rows(prediction_path), prediction_path.read_bytes()


def run_candidate(input_dir):
    return run_candidate_artifact(input_dir)[0]


def validated_probabilities(input_dir, predictions=None):
    if predictions is None:
        predictions = run_candidate(input_dir)
    candidates = read_rows(os.path.join(input_dir, "evaluation_candidates.csv"))
    expected = {(row["event_id"], row["item_id"]) for row in candidates}
    assert predictions
    assert list(predictions[0]) == FIELDS
    assert len(predictions) == len(expected)
    actual = [(row["event_id"], row["item_id"]) for row in predictions]
    assert len(actual) == len(set(actual))
    assert set(actual) == expected
    probabilities = {}
    totals = {}
    for row in predictions:
        probability = float(row["probability"])
        assert math.isfinite(probability)
        assert 0.0 <= probability <= 1.0
        key = (row["event_id"], row["item_id"])
        probabilities[key] = probability
        totals[row["event_id"]] = totals.get(row["event_id"], 0.0) + probability
    assert all(abs(total - 1.0) < 1e-8 for total in totals.values())
    return probabilities


def hidden_rows():
    hidden = read_rows("/tests/hidden_choices.csv")
    assert len(hidden) >= 60
    return {row["event_id"]: row for row in hidden}


def metrics(probabilities, hidden, event_ids):
    loss = reciprocal_rank = recall_at_three = total_weight = 0.0
    candidates = {}
    for (event_id, item_id), probability in probabilities.items():
        candidates.setdefault(event_id, []).append((item_id, probability))
    for event_id in event_ids:
        target = hidden[event_id]["clicked_item"]
        weight = float(hidden[event_id]["metric_weight"])
        ranked = sorted(
            candidates[event_id],
            key=lambda pair: (-pair[1], pair[0]),
        )
        target_probability = dict(ranked)[target]
        rank = next(
            index for index, (item_id, _) in enumerate(ranked, 1) if item_id == target
        )
        loss += weight * -math.log(max(target_probability, 1e-12))
        reciprocal_rank += weight / rank
        recall_at_three += weight * (rank <= 3)
        total_weight += weight
    return (
        loss / total_weight,
        reciprocal_rank / total_weight,
        recall_at_three / total_weight,
    )


@cache
def base_probabilities():
    return validated_probabilities(PUBLIC_INPUT, base_artifact()[0])


@cache
def base_artifact():
    return run_candidate_artifact(PUBLIC_INPUT)


def keyed_digest(prefix, value):
    digest = hashlib.sha256(f"{prefix}:{value}".encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"


@cache
def reordered_probabilities():
    bundle = tempfile.mkdtemp(prefix="choice-reordered-")
    shutil.copytree("/app/data", bundle, dirs_exist_ok=True)
    os.chmod(bundle, 0o755)
    event_map = {}
    for relation in ("training_choices.csv", "evaluation_choices.csv"):
        for row in read_rows(os.path.join(bundle, relation)):
            event_map[row["event_id"]] = keyed_digest("event", row["event_id"])
    rng = random.Random(20260726)
    for relation in RELATIONS:
        path = os.path.join(bundle, relation)
        rows = read_rows(path)
        for row in rows:
            row["event_id"] = event_map[row["event_id"]]
        rng.shuffle(rows)
        write_rows(path, rows)
    transformed = validated_probabilities(bundle)
    inverse = {value: key for key, value in event_map.items()}
    return {
        (inverse[event_id], item_id): probability
        for (event_id, item_id), probability in transformed.items()
    }


@cache
def cold_start_surface():
    bundle = tempfile.mkdtemp(prefix="choice-cold-start-")
    shutil.copytree("/app/data", bundle, dirs_exist_ok=True)
    os.chmod(bundle, 0o755)
    path = os.path.join(bundle, "evaluation_candidates.csv")
    candidates = read_rows(path)
    item_ids = sorted({int(row["item_id"]) for row in candidates})
    item_map = {str(item_id): str(900_000 + item_id) for item_id in item_ids}
    rng = random.Random(41017)
    for row in candidates:
        row["item_id"] = item_map[row["item_id"]]
    rng.shuffle(candidates)
    write_rows(path, candidates)
    choices_path = os.path.join(bundle, "evaluation_choices.csv")
    choices = read_rows(choices_path)
    rng.shuffle(choices)
    write_rows(choices_path, choices)
    probabilities = validated_probabilities(bundle)
    transformed_hidden = {
        event_id: {
            **row,
            "clicked_item": item_map[row["clicked_item"]],
        }
        for event_id, row in hidden_rows().items()
    }
    return probabilities, transformed_hidden


EVALUATION_CANDIDATES = read_rows("/app/data/evaluation_candidates.csv")
EVALUATION_ITEMS = {}
for candidate in EVALUATION_CANDIDATES:
    EVALUATION_ITEMS.setdefault(candidate["event_id"], set()).add(candidate["item_id"])
EVALUATION_EVENT_IDS = sorted(EVALUATION_ITEMS)


@pytest.mark.parametrize("event_id", EVALUATION_EVENT_IDS)
def test_output_contract_on_each_later_choice(event_id):
    """This later event receives its ten valid normalized item probabilities."""
    probabilities = base_probabilities()
    observed = {
        item_id: probability
        for (candidate_event, item_id), probability in probabilities.items()
        if candidate_event == event_id
    }
    assert set(observed) == EVALUATION_ITEMS[event_id]
    assert len(observed) == 10
    assert all(
        math.isfinite(value) and 0.0 <= value <= 1.0 for value in observed.values()
    )
    assert sum(observed.values()) == pytest.approx(1.0, abs=1e-8)


def test_overall_exposure_corrected_choice_quality():
    """Exposure-weighted hidden choices clear all three overall quality bars."""
    hidden = hidden_rows()
    score = metrics(base_probabilities(), hidden, sorted(hidden))
    assert score[0] < 1.31
    assert score[1] > 0.68
    assert score[2] > 0.81


def test_quality_holds_across_campaign_and_logger_groups():
    """No campaign or logger group can hide behind a strong aggregate score."""
    hidden = hidden_rows()
    events = {
        row["event_id"]: row for row in read_rows("/app/data/evaluation_choices.csv")
    }
    campaign_scores = []
    for campaign in sorted({row["campaign"] for row in events.values()}):
        event_ids = [
            event_id for event_id in hidden if events[event_id]["campaign"] == campaign
        ]
        assert len(event_ids) >= 25
        campaign_scores.append(metrics(base_probabilities(), hidden, event_ids))
    assert max(score[0] for score in campaign_scores) < 1.85
    assert min(score[1] for score in campaign_scores) > 0.55
    assert min(score[2] for score in campaign_scores) > 0.61

    logger_scores = []
    for logger in sorted({row["logger"] for row in events.values()}):
        event_ids = [
            event_id for event_id in hidden if events[event_id]["logger"] == logger
        ]
        assert len(event_ids) >= 50
        logger_scores.append(metrics(base_probabilities(), hidden, event_ids))
    assert max(score[0] for score in logger_scores) < 1.45
    assert min(score[1] for score in logger_scores) > 0.62
    assert min(score[2] for score in logger_scores) > 0.78


def test_quality_holds_across_capped_and_uncapped_exposure():
    """Both exposure-weight regimes retain calibrated ranking quality."""
    hidden = hidden_rows()
    capped = [
        event_id
        for event_id, row in hidden.items()
        if float(row["metric_weight"]) >= 10.0 - 1e-12
    ]
    uncapped = [
        event_id
        for event_id, row in hidden.items()
        if float(row["metric_weight"]) < 10.0 - 1e-12
    ]
    assert len(capped) >= 30
    assert len(uncapped) >= 30
    scores = [
        metrics(base_probabilities(), hidden, capped),
        metrics(base_probabilities(), hidden, uncapped),
    ]
    assert max(score[0] for score in scores) < 1.41
    assert min(score[1] for score in scores) > 0.64
    assert min(score[2] for score in scores) > 0.80


def test_item_features_transfer_to_cold_start_identifiers():
    """Replacing evaluation item keys preserves transferable feature quality."""
    probabilities, hidden = cold_start_surface()
    score = metrics(probabilities, hidden, sorted(hidden))
    assert score[0] < 1.45
    assert score[1] > 0.64
    assert score[2] > 0.78


def test_relation_order_and_opaque_event_keys_are_equivariant():
    """Relation permutations and renamed event keys preserve keyed predictions."""
    original = base_probabilities()
    transformed = reordered_probabilities()
    assert original.keys() == transformed.keys()
    assert max(abs(original[key] - transformed[key]) for key in original) < 1e-7


def test_default_invocation_and_repeated_bytes_are_deterministic():
    """Default paths and identical inputs reproduce the primary output bytes."""
    output = Path("/app/outputs")
    output.mkdir(exist_ok=True)
    output.chmod(0o777)
    prediction_path = output / "choice_predictions.csv"
    prediction_path.unlink(missing_ok=True)
    environment = dict(os.environ, HOME=str(output), TMPDIR=str(output))
    result = subprocess.run(
        sandbox_command(PUBLIC_INPUT, output, ["/app/run.sh"]),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        cwd="/app",
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert prediction_path.read_bytes() == base_artifact()[1]
    assert run_candidate_artifact(PUBLIC_INPUT)[1] == base_artifact()[1]


def test_candidate_cannot_read_private_verifier_surfaces():
    """Candidate execution cannot inspect labels, rewards, or reference code."""
    output = Path(tempfile.mkdtemp(prefix="choice-sandbox-", dir="/dev/shm"))
    output.chmod(0o777)
    for protected_path in [
        "/tests/hidden_choices.csv",
        "/logs/verifier/reward.txt",
        "/solution/reference_analysis.R",
    ]:
        result = subprocess.run(
            sandbox_command(
                PUBLIC_INPUT,
                output,
                ["/usr/bin/head", "-c", "1", protected_path],
            ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode != 0
