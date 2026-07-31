import csv
import math
import subprocess
from functools import cache
from pathlib import Path

CLASSES = [
    "conversation_service",
    "share_amplify",
    "emotion_nurture",
    "routine_watch",
]
CLASS_INDEX = {route: index for index, route in enumerate(CLASSES)}
PROB_COLUMNS = [f"prob_{route}" for route in CLASSES]
OUTPUT_PATH = Path("/app/outputs/response_route_probabilities.csv")
SCORER_PATH = Path("/app/score_response_routes.R")
LABEL_PATH = Path("/tests/hidden_response_routes.csv")
EVAL_PATH = Path("/app/data/evaluation_posts.csv")
TRAIN_PATH = Path("/app/data/training_posts.csv")
REPLAY_ROUTE_MAP = {
    "conversation_service": "share_amplify",
    "share_amplify": "emotion_nurture",
    "emotion_nurture": "routine_watch",
    "routine_watch": "conversation_service",
}


def _to_float(value):
    try:
        result = float(value)
    except ValueError:
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return result


def _rotate_route(route, offset):
    return CLASSES[(CLASS_INDEX[route] + offset) % len(CLASSES)]


def _segment_replay_label(row, base_label):
    reactions = max(1.0, _to_float(row["num_reactions"]))
    loves = _to_float(row["num_loves"])
    shares = _to_float(row["num_shares"])
    comments = _to_float(row["num_comments"])
    hour = _to_float(row["published_hour"])
    content = row["logged_content_route"]
    stratum = row["priority_stratum"]
    if stratum == "low_support":
        return _rotate_route(base_label, 2 if content == "text_status" else 3)
    if stratum == "policy_shift":
        return _rotate_route(
            base_label, 1 if hour < 6 or loves / reactions > 0.18 else 2
        )
    if content == "product_photo" and shares > comments:
        return _rotate_route(base_label, 3)
    return _rotate_route(base_label, 1)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@cache
def _run_candidate():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()
    result = subprocess.run(
        ["Rscript", "/app/analysis.R"],
        cwd="/app",
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert OUTPUT_PATH.exists(), "response_route_probabilities.csv was not created"
    labels = _read_csv(LABEL_PATH)
    eval_rows = _read_csv(EVAL_PATH)
    predictions = _read_csv(OUTPUT_PATH)
    return labels, eval_rows, predictions


def _parse_prediction_rows(labels, eval_rows, predictions):
    label_by_id = {row["post_id"]: row for row in labels}
    eval_ids = [row["post_id"] for row in eval_rows]
    assert len(predictions) == len(eval_ids)
    assert {row["post_id"] for row in predictions} == set(eval_ids)
    assert len({row["post_id"] for row in predictions}) == len(predictions)
    parsed = []
    for row in predictions:
        assert list(row.keys()) == ["post_id", *PROB_COLUMNS]
        probs = {}
        total = 0.0
        for column, route in zip(PROB_COLUMNS, CLASSES, strict=True):
            value = float(row[column])
            assert math.isfinite(value)
            assert -1e-12 <= value <= 1.0 + 1e-12
            probs[route] = min(1.0, max(0.0, value))
            total += value
        assert abs(total - 1.0) <= 1e-6
        truth = label_by_id[row["post_id"]]
        parsed.append(
            {
                "post_id": row["post_id"],
                "label": truth["response_route"],
                "weight": float(truth["target_policy_weight"]),
                "stratum": truth["priority_stratum"],
                "probs": probs,
            }
        )
    return parsed


def _parse_predictions():
    labels, eval_rows, predictions = _run_candidate()
    return _parse_prediction_rows(labels, eval_rows, predictions)


def _metrics(rows):
    weight_sum = sum(row["weight"] for row in rows)
    log_loss = 0.0
    brier = 0.0
    top1 = 0.0
    for row in rows:
        label = row["label"]
        probs = row["probs"]
        weight = row["weight"]
        log_loss += weight * -math.log(max(probs[label], 1e-15))
        brier += weight * sum(
            (probs[route] - (1.0 if route == label else 0.0)) ** 2 for route in CLASSES
        )
        predicted = max(CLASSES, key=lambda route: probs[route])
        top1 += weight * (1.0 if predicted == label else 0.0)
    return {
        "log_loss": log_loss / weight_sum,
        "brier": brier / weight_sum,
        "top1": top1 / weight_sum,
        "n": len(rows),
    }


def _baseline_rows(kind):
    labels = _read_csv(LABEL_PATH)
    eval_rows = _read_csv(EVAL_PATH)
    train_rows = _read_csv(TRAIN_PATH)
    counts = {route: 1.0 for route in CLASSES}
    route_by_content = {}
    for row in train_rows:
        counts[row["response_route"]] += 1.0
        content = row["logged_content_route"]
        route_by_content.setdefault(content, {route: 1.0 for route in CLASSES})
        route_by_content[content][row["response_route"]] += 1.0
    total = sum(counts.values())
    prior = {route: counts[route] / total for route in CLASSES}
    label_by_id = {row["post_id"]: row for row in labels}
    out = []
    for row in eval_rows:
        if kind == "prior":
            probs = dict(prior)
        else:
            content_counts = route_by_content[row["logged_content_route"]]
            route = max(CLASSES, key=lambda item: content_counts[item])
            probs = {item: 0.05 for item in CLASSES}
            probs[route] = 0.85
        truth = label_by_id[row["post_id"]]
        out.append(
            {
                "post_id": row["post_id"],
                "label": truth["response_route"],
                "weight": float(truth["target_policy_weight"]),
                "stratum": truth["priority_stratum"],
                "probs": probs,
            }
        )
    return out


def _write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _scorer_replay_rows(tmp_path, mode):
    labels = _read_csv(LABEL_PATH)
    eval_rows = _read_csv(EVAL_PATH)
    label_by_id = {row["post_id"]: row for row in labels}
    train_fields = [*eval_rows[0].keys(), "response_route"]
    eval_fields = list(eval_rows[0].keys())
    replay_train = []
    replay_eval = []
    replay_labels = []
    for index, row in enumerate(eval_rows):
        replay_row = dict(row)
        replay_row["post_id"] = f"{mode.upper()}{index:04d}"
        label = label_by_id[row["post_id"]]
        replay_weight = _to_float(label["target_policy_weight"])
        if mode == "segment" and label["priority_stratum"] == "low_support":
            replay_weight *= 1.55
        elif mode == "segment" and label["priority_stratum"] == "policy_shift":
            replay_weight *= 1.20
        replay_row["target_policy_weight"] = f"{replay_weight:.6f}"
        response_route = (
            _segment_replay_label(row, label["response_route"])
            if mode == "segment"
            else REPLAY_ROUTE_MAP[label["response_route"]]
        )
        replay_label = {
            "post_id": replay_row["post_id"],
            "response_route": response_route,
            "target_policy_weight": f"{replay_weight:.6f}",
            "priority_stratum": label["priority_stratum"],
        }
        if mode == "segment":
            held_out = index % 3 == 1 or (
                row["logged_content_route"] == "link_teaser" and index % 2 == 0
            )
        else:
            held_out = index % 4 == 2
        if held_out:
            replay_eval.append(replay_row)
            replay_labels.append(replay_label)
        else:
            replay_train.append(
                {**replay_row, "response_route": replay_label["response_route"]}
            )

    input_dir = tmp_path / "replay_input"
    output_dir = tmp_path / "replay_output"
    input_dir.mkdir()
    output_dir.mkdir()
    _write_csv(input_dir / "training_posts.csv", replay_train, train_fields)
    _write_csv(input_dir / "evaluation_posts.csv", replay_eval, eval_fields)
    assert SCORER_PATH.exists(), "missing /app/score_response_routes.R"
    result = subprocess.run(
        ["Rscript", str(SCORER_PATH), str(input_dir), str(output_dir)],
        cwd="/app",
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    predictions = _read_csv(output_dir / "response_route_probabilities.csv")
    return _parse_prediction_rows(replay_labels, replay_eval, predictions)


def test_probability_file_covers_every_held_out_post():
    """Each held-out post needs exactly one normalized response-route vector."""
    parsed = _parse_predictions()
    assert len(parsed) == 880
    assert {row["label"] for row in parsed} == set(CLASSES)


def test_policy_weighted_overall_response_quality():
    """Weighted held-out prediction must be calibrated and accurate enough."""
    metrics = _metrics(_parse_predictions())
    assert metrics["log_loss"] <= 0.65
    assert metrics["brier"] <= 0.35
    assert metrics["top1"] >= 0.78


def test_policy_shift_posts_keep_calibrated_predictions():
    """Upweighted live-video policy-shift rows need their own reward margin."""
    rows = [row for row in _parse_predictions() if row["stratum"] == "policy_shift"]
    metrics = _metrics(rows)
    assert metrics["n"] == 303
    assert metrics["log_loss"] <= 0.62
    assert metrics["brier"] <= 0.36
    assert metrics["top1"] >= 0.78


def test_low_support_content_routes_are_not_discarded():
    """Sparse text and link content routes still need useful probabilities."""
    rows = [row for row in _parse_predictions() if row["stratum"] == "low_support"]
    metrics = _metrics(rows)
    assert metrics["n"] == 63
    assert metrics["brier"] <= 0.53
    assert metrics["top1"] >= 0.70


def test_shortcut_controls_miss_the_reward_band():
    """Class priors and logged-content replay should not satisfy the task."""
    prior = _metrics(_baseline_rows("prior"))
    logged = _metrics(_baseline_rows("logged"))
    assert prior["log_loss"] > 1.20 or prior["top1"] < 0.45
    assert logged["brier"] > 0.70 or logged["top1"] < 0.45


def test_reusable_scorer_generalizes_on_shifted_replay(tmp_path):
    """The reusable scorer must refit on a verifier-held response-route split."""
    metrics = _metrics(_scorer_replay_rows(tmp_path, "replay"))
    assert metrics["n"] == 220
    assert metrics["log_loss"] <= 0.94
    assert metrics["brier"] <= 0.52
    assert metrics["top1"] >= 0.62


def test_reusable_scorer_handles_segment_shifted_replay(tmp_path):
    """The scorer must adapt when priority and content segments shift labels."""
    metrics = _metrics(_scorer_replay_rows(tmp_path, "segment"))
    assert metrics["n"] == 293
    assert metrics["log_loss"] <= 0.94
    assert metrics["brier"] <= 0.52
    assert metrics["top1"] >= 0.62
