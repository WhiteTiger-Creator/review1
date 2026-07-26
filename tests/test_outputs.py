"""Behavioral tests for the grouped Weka evaluation command."""

import json
import math
import random
import re
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

APP = Path("/app")
COMMAND = APP / "bin" / "weka-cv-audit"


def _quoted(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _write_arff(
    path: Path,
    classes: list[str],
    rows: list[dict],
    *,
    class_name: str = "outcome",
    id_name: str = "sample_id",
    group_name: str = "site",
    feature_names: list[str] | None = None,
) -> None:
    feature_names = feature_names or [
        f"feature_{index + 1}" for index in range(len(rows[0]["features"]))
    ]
    lines = [
        "@relation 'grouped audit'",
        "",
        f"@attribute {_quoted(id_name)} string",
        f"@attribute {_quoted(group_name)} string",
    ]
    lines.extend(f"@attribute {_quoted(name)} numeric" for name in feature_names)
    class_values = ",".join(_quoted(value) for value in classes)
    lines.extend(
        [
            f"@attribute {_quoted(class_name)} {{{class_values}}}",
            "",
            "@data",
        ]
    )
    for row in rows:
        values = [
            "?" if row["id"] is None else _quoted(row["id"]),
            "?" if row["group"] is None else _quoted(row["group"]),
        ]
        values.extend(
            "?" if value is None else repr(float(value)) for value in row["features"]
        )
        values.append("?" if row["class"] is None else _quoted(row["class"]))
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _six(value: float) -> float:
    rounded = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return float(rounded)


def _transform(
    row: dict, means: list[float], scales: list[float]
) -> list[float]:
    vector = []
    for feature, (mean, scale) in enumerate(zip(means, scales, strict=True)):
        value = row["features"][feature]
        if value is None:
            value = mean
        vector.append((value - mean) / scale)
    return vector


def _fisher_scores(
    training_vectors: list[list[float]],
    class_indices: list[int],
    feature_count: int,
    class_count: int,
) -> list[float]:
    scores = []
    for feature in range(feature_count):
        values = [vector[feature] for vector in training_vectors]
        global_mean = sum(values) / len(values)
        class_sums = [0.0] * class_count
        class_counts = [0] * class_count
        for value, class_index in zip(values, class_indices, strict=True):
            class_sums[class_index] += value
            class_counts[class_index] += 1
        class_means = [
            class_sums[class_index] / class_counts[class_index]
            if class_counts[class_index]
            else 0.0
            for class_index in range(class_count)
        ]
        between = sum(
            class_counts[class_index]
            * (class_means[class_index] - global_mean) ** 2
            for class_index in range(class_count)
        )
        within = sum(
            (value - class_means[class_index]) ** 2
            for value, class_index in zip(values, class_indices, strict=True)
        )
        if within == 0.0:
            scores.append(float("inf") if between > 0.0 else 0.0)
        else:
            scores.append(between / within)
    return scores


def _rank_features(scores: list[float]) -> list[int]:
    return sorted(
        range(len(scores)),
        key=lambda index: (
            0 if math.isinf(scores[index]) and scores[index] > 0 else 1,
            -scores[index] if not math.isinf(scores[index]) else 0.0,
            index,
        ),
    )


def _expected(
    data_path: Path,
    classes: list[str],
    rows: list[dict],
    *,
    class_name: str = "outcome",
    top: int | None = None,
    feature_names: list[str] | None = None,
) -> dict:
    labeled = [row for row in rows if row["class"] is not None]
    groups = sorted({row["group"] for row in labeled})
    class_index = {label: index for index, label in enumerate(classes)}
    feature_count = len(labeled[0]["features"])
    if feature_names is None:
        feature_names = [f"feature_{index + 1}" for index in range(feature_count)]
    if top is None:
        top = feature_count
    predictions = []
    folds = []

    for held_out in groups:
        training = [row for row in labeled if row["group"] != held_out]
        test = [row for row in labeled if row["group"] == held_out]

        means = []
        for feature in range(feature_count):
            present = [
                row["features"][feature]
                for row in training
                if row["features"][feature] is not None
            ]
            means.append(sum(present) / len(present) if present else 0.0)

        scales = []
        for feature in range(feature_count):
            values = [
                means[feature]
                if row["features"][feature] is None
                else row["features"][feature]
                for row in training
            ]
            variance = sum((value - means[feature]) ** 2 for value in values) / len(
                values
            )
            scale = math.sqrt(variance)
            scales.append(1.0 if scale == 0.0 else scale)

        training_vectors = [_transform(row, means, scales) for row in training]
        training_classes = [class_index[row["class"]] for row in training]
        scores = _fisher_scores(
            training_vectors,
            training_classes,
            feature_count,
            len(classes),
        )
        selected = _rank_features(scores)[:top]

        centroids = [[0.0] * len(selected) for _ in classes]
        class_sizes = [0] * len(classes)
        for row, vector in zip(training, training_vectors, strict=True):
            index = class_index[row["class"]]
            class_sizes[index] += 1
            for position, feature in enumerate(selected):
                centroids[index][position] += vector[feature]
        for index in range(len(classes)):
            if class_sizes[index]:
                centroids[index] = [
                    value / class_sizes[index] for value in centroids[index]
                ]

        fold_correct = 0
        for row in test:
            vector = _transform(row, means, scales)
            distances = [
                sum(
                    (vector[feature] - centroid[position]) ** 2
                    for position, feature in enumerate(selected)
                )
                for centroid in centroids
            ]
            minimum = min(distances)
            distance_scores = [math.exp(-(distance - minimum)) for distance in distances]
            total = sum(distance_scores)
            probabilities = [score / total for score in distance_scores]
            predicted = max(range(len(classes)), key=probabilities.__getitem__)
            actual = class_index[row["class"]]
            fold_correct += predicted == actual
            predictions.append(
                {
                    "id": row["id"],
                    "group": row["group"],
                    "actual": row["class"],
                    "predicted": classes[predicted],
                    "confidence": _six(probabilities[predicted]),
                    "_actual_index": actual,
                    "_predicted_index": predicted,
                    "_actual_probability": probabilities[actual],
                }
            )
        folds.append(
            {
                "group": held_out,
                "train": len(training),
                "test": len(test),
                "accuracy": _six(fold_correct / len(test)),
                "selectedFeatures": [feature_names[feature] for feature in selected],
            }
        )

    predictions.sort(key=lambda item: item["id"])
    confusion = [[0] * len(classes) for _ in classes]
    correct = 0
    loss = 0.0
    for prediction in predictions:
        actual = prediction["_actual_index"]
        predicted = prediction["_predicted_index"]
        confusion[actual][predicted] += 1
        correct += actual == predicted
        loss -= math.log(max(prediction["_actual_probability"], 1.0e-15))

    f1_values = []
    for index in range(len(classes)):
        true_positive = confusion[index][index]
        predicted_count = sum(row[index] for row in confusion)
        actual_count = sum(confusion[index])
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / actual_count if actual_count else 0.0
        f1_values.append(
            0.0
            if precision + recall == 0.0
            else 2.0 * precision * recall / (precision + recall)
        )

    public_predictions = [
        {key: value for key, value in prediction.items() if not key.startswith("_")}
        for prediction in predictions
    ]
    return {
        "dataset": data_path.name,
        "instances": len(labeled),
        "classAttribute": class_name,
        "classes": classes,
        "folds": folds,
        "metrics": {
            "accuracy": _six(correct / len(predictions)),
            "macroF1": _six(sum(f1_values) / len(classes)),
            "logLoss": _six(loss / len(predictions)),
        },
        "confusion": confusion,
        "predictions": public_predictions,
    }


def _run(
    data_path: Path,
    output_path: Path,
    *,
    class_name: str = "outcome",
    id_name: str = "sample_id",
    group_name: str = "site",
    top: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(COMMAND),
            "--group",
            group_name,
            "--data",
            str(data_path),
            "--out",
            str(output_path),
            "--id",
            id_name,
            "--class",
            class_name,
            "--top",
            str(top),
        ],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )


def _assert_matches(
    tmp_path: Path,
    classes: list[str],
    rows: list[dict],
    *,
    class_name: str = "outcome",
    id_name: str = "sample_id",
    group_name: str = "site",
    feature_names: list[str] | None = None,
    top: int | None = None,
) -> tuple[dict, str]:
    data_path = tmp_path / "input.arff"
    output_path = tmp_path / "report.json"
    feature_count = len(rows[0]["features"])
    if top is None:
        top = feature_count
    _write_arff(
        data_path,
        classes,
        rows,
        class_name=class_name,
        id_name=id_name,
        group_name=group_name,
        feature_names=feature_names,
    )
    result = _run(
        data_path,
        output_path,
        class_name=class_name,
        id_name=id_name,
        group_name=group_name,
        top=top,
    )
    assert result.returncode == 0, result.stderr
    raw = output_path.read_text(encoding="utf-8")
    actual = json.loads(raw)
    assert actual == _expected(
        data_path,
        classes,
        rows,
        class_name=class_name,
        top=top,
        feature_names=feature_names,
    )
    return actual, raw


def _balanced_rows() -> list[dict]:
    rows = []
    values = {
        "west": [(0.2, "cold"), (0.6, "cold"), (3.8, "warm"), (4.2, "warm")],
        "east": [(0.0, "cold"), (0.9, "cold"), (3.5, "warm"), (4.5, "warm")],
        "north": [(0.4, "cold"), (1.1, "cold"), (3.6, "warm"), (4.0, "warm")],
    }
    for group, group_values in values.items():
        for index, (feature, label) in enumerate(group_values):
            rows.append(
                {
                    "id": f"{group}-{index}",
                    "group": group,
                    "features": [feature, feature * 0.7 + index * 0.1],
                    "class": label,
                }
            )
    return rows


def test_cli_help_and_bad_syntax(tmp_path):
    """The command exposes its fixed option interface and rejects malformed syntax."""
    help_result = subprocess.run(
        [str(COMMAND), "--help"],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert help_result.returncode == 0
    assert help_result.stdout.startswith("usage: /app/bin/weka-cv-audit ")

    bad_result = subprocess.run(
        [str(COMMAND), "--data", str(tmp_path / "missing.arff")],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert bad_result.returncode == 2
    assert bad_result.stderr.startswith("error: ")

    duplicate_group = subprocess.run(
        [
            str(COMMAND),
            "--data",
            str(tmp_path / "missing.arff"),
            "--class",
            "outcome",
            "--id",
            "sample_id",
            "--group",
            "site",
            "--out",
            str(tmp_path / "report.json"),
            "--top",
            "2",
            "--group",
            "site",
        ],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert duplicate_group.returncode == 2
    assert "duplicate option: --group" in duplicate_group.stderr

    duplicate_top = subprocess.run(
        [
            str(COMMAND),
            "--data",
            str(tmp_path / "missing.arff"),
            "--class",
            "outcome",
            "--id",
            "sample_id",
            "--group",
            "site",
            "--out",
            str(tmp_path / "report.json"),
            "--top",
            "2",
            "--top",
            "1",
        ],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert duplicate_top.returncode == 2
    assert "duplicate option: --top" in duplicate_top.stderr

    non_integer_top = subprocess.run(
        [
            str(COMMAND),
            "--data",
            str(tmp_path / "missing.arff"),
            "--class",
            "outcome",
            "--id",
            "sample_id",
            "--group",
            "site",
            "--out",
            str(tmp_path / "report.json"),
            "--top",
            "two",
        ],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert non_integer_top.returncode == 2
    assert non_integer_top.stderr.startswith("error: ")


def test_bundled_example_matches_the_contract(tmp_path):
    """The supplied ARFF example produces the complete deterministic report."""
    rows = [
        {"id": "a-01", "group": "lab-a", "features": [1.0, 1.2], "class": "moss"},
        {"id": "a-02", "group": "lab-a", "features": [1.3, None], "class": "moss"},
        {"id": "a-03", "group": "lab-a", "features": [3.8, 4.1], "class": "fern"},
        {"id": "a-04", "group": "lab-a", "features": [4.2, 3.9], "class": "fern"},
        {"id": "b-01", "group": "lab-b", "features": [0.8, 1.1], "class": "moss"},
        {"id": "b-02", "group": "lab-b", "features": [1.4, 1.0], "class": "moss"},
        {"id": "b-03", "group": "lab-b", "features": [3.6, 3.7], "class": "fern"},
        {"id": "b-04", "group": "lab-b", "features": [4.4, 4.2], "class": "fern"},
        {"id": "c-01", "group": "lab-c", "features": [0.9, 0.7], "class": "moss"},
        {"id": "c-02", "group": "lab-c", "features": [1.5, 1.4], "class": "moss"},
        {"id": "c-03", "group": "lab-c", "features": [3.9, 3.6], "class": "fern"},
        {"id": "c-04", "group": "lab-c", "features": [4.1, None], "class": "fern"},
        {"id": None, "group": None, "features": [9.0, 9.0], "class": None},
    ]
    output_path = tmp_path / "sample-report.json"
    result = _run(
        APP / "examples" / "sites.arff",
        output_path,
        class_name="species",
        id_name="sample_id",
        group_name="site",
        top=2,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output_path.read_text()) == _expected(
        APP / "examples" / "sites.arff",
        ["moss", "fern"],
        rows,
        class_name="species",
        top=2,
        feature_names=["height", "moisture"],
    )


def test_fold_local_preprocessing_and_training(tmp_path):
    """Held-out groups do not influence imputation, scaling, or class centroids."""
    rows = []
    group_values = {
        "g1": [(0.0, "a"), (1.0, "a"), (9.0, "b"), (10.0, "b")],
        "g2": [(0.2, "a"), (1.2, "a"), (8.8, "b"), (10.2, "b")],
        "g3": [(9.5, "a"), (8.7, "a"), (0.4, "b"), (1.1, "b")],
    }
    for group, values in group_values.items():
        for index, (value, label) in enumerate(values):
            rows.append(
                {
                    "id": f"{group}-{index}",
                    "group": group,
                    "features": [value, None if index == 1 else value * 100],
                    "class": label,
                }
            )
    report, _ = _assert_matches(tmp_path, ["a", "b"], rows, top=2)
    assert any(
        item["actual"] != item["predicted"] for item in report["predictions"]
    )


def test_fold_local_fisher_feature_selection_ignores_held_out_group(tmp_path):
    """Held-out rows cannot change Fisher scores or the predictors chosen for a fold."""
    feature_names = ["signal", "decoy"]
    rows = [
        {"id": "g1-a1", "group": "g1", "features": [0.0, 0.0], "class": "alpha"},
        {"id": "g1-a2", "group": "g1", "features": [0.2, 0.0], "class": "alpha"},
        {"id": "g1-b1", "group": "g1", "features": [10.0, 0.0], "class": "beta"},
        {"id": "g1-b2", "group": "g1", "features": [10.2, 0.0], "class": "beta"},
        {"id": "g2-a1", "group": "g2", "features": [100.0, 0.0], "class": "alpha"},
        {"id": "g2-a2", "group": "g2", "features": [100.2, 0.0], "class": "alpha"},
        {"id": "g2-b1", "group": "g2", "features": [100.0, 100.0], "class": "beta"},
        {"id": "g2-b2", "group": "g2", "features": [100.2, 100.0], "class": "beta"},
        {"id": "g3-a1", "group": "g3", "features": [0.0, 0.0], "class": "alpha"},
        {"id": "g3-a2", "group": "g3", "features": [0.2, 0.0], "class": "alpha"},
        {"id": "g3-b1", "group": "g3", "features": [10.0, 0.0], "class": "beta"},
        {"id": "g3-b2", "group": "g3", "features": [10.2, 0.0], "class": "beta"},
    ]
    report, _ = _assert_matches(
        tmp_path,
        ["alpha", "beta"],
        rows,
        feature_names=feature_names,
        top=1,
    )
    expected = _expected(
        tmp_path / "input.arff",
        ["alpha", "beta"],
        rows,
        feature_names=feature_names,
        top=1,
    )
    for actual_fold, expected_fold in zip(report["folds"], expected["folds"], strict=True):
        assert actual_fold["selectedFeatures"] == expected_fold["selectedFeatures"]
    g2_fold = next(fold for fold in report["folds"] if fold["group"] == "g2")
    assert g2_fold["selectedFeatures"] == ["signal"]


def test_fisher_score_ties_use_arff_predictor_order(tmp_path):
    """Equal Fisher scores rank earlier ARFF predictors ahead of later ones."""
    feature_names = ["first", "second", "third"]
    rows = []
    for group in ["g1", "g2"]:
        for index, label in enumerate(["low", "high"]):
            value = float(index * 5 + 1)
            rows.append(
                {
                    "id": f"{group}-{label}",
                    "group": group,
                    "features": [value, value, value + 0.001],
                    "class": label,
                }
            )
    report, _ = _assert_matches(
        tmp_path,
        ["low", "high"],
        rows,
        feature_names=feature_names,
        top=2,
    )
    for fold in report["folds"]:
        assert fold["selectedFeatures"] == ["first", "second"]


def test_missing_values_zero_variance_and_three_classes(tmp_path):
    """Fold statistics handle absent values, constant predictors, and all classes."""
    rows = []
    for group_index, group in enumerate(["gamma", "alpha", "beta"]):
        for class_index, label in enumerate(["red", "green", "blue"]):
            rows.append(
                {
                    "id": f"{label}-{group}",
                    "group": group,
                    "features": [
                        class_index * 2.0 + group_index * 0.2,
                        None if group != "gamma" else class_index + 0.5,
                        7.0,
                    ],
                    "class": label,
                }
            )
    _assert_matches(tmp_path, ["red", "green", "blue"], rows, top=3)


def test_unlabeled_rows_are_discarded_before_validation(tmp_path):
    """An unlabeled row has no effect even when its id and group are missing."""
    rows = _balanced_rows()
    rows.extend(
        [
            {"id": None, "group": None, "features": [999.0, None], "class": None},
            {
                "id": "west-0",
                "group": "west",
                "features": [-999.0, -999.0],
                "class": None,
            },
        ]
    )
    report, _ = _assert_matches(tmp_path, ["cold", "warm"], rows, top=2)
    assert report["instances"] == 12
    assert len(report["predictions"]) == 12


def test_macro_f1_confidence_and_log_loss(tmp_path):
    """Metrics use class-macro F1 and probabilities for their documented roles."""
    rows = []
    for group_index, group in enumerate(["one", "two", "three"]):
        for index in range(5):
            rows.append(
                {
                    "id": f"{group}-major-{index}",
                    "group": group,
                    "features": [index * 0.2 + group_index],
                    "class": "major",
                }
            )
        rows.append(
            {
                "id": f"{group}-minor",
                "group": group,
                "features": [group_index + 0.3],
                "class": "minor",
            }
        )
    report, _ = _assert_matches(tmp_path, ["major", "minor"], rows, top=1)
    assert any(
        item["actual"] != item["predicted"] for item in report["predictions"]
    )


def test_equal_distances_prefer_class_declaration_order(tmp_path):
    """Exact probability ties select the earlier declared class with confidence one half."""
    rows = []
    for group in ["g3", "g1", "g2"]:
        for label in ["first", "second"]:
            rows.append(
                {
                    "id": f"{group}-{label}",
                    "group": group,
                    "features": [4.0, 4.0],
                    "class": label,
                }
            )
    report, _ = _assert_matches(tmp_path, ["first", "second"], rows, top=2)
    assert {item["predicted"] for item in report["predictions"]} == {"first"}
    assert {item["confidence"] for item in report["predictions"]} == {0.5}


def test_report_order_names_and_fixed_decimal_rendering(tmp_path):
    """Names are resolved literally and report arrays and decimals are canonical."""
    rows = _balanced_rows()
    random.Random(91).shuffle(rows)
    report, raw = _assert_matches(
        tmp_path,
        ["cold", "warm"],
        rows,
        class_name="target label",
        id_name="sample key",
        group_name="collection site",
        feature_names=["signal one", "signal two"],
        top=2,
    )
    assert [fold["group"] for fold in report["folds"]] == ["east", "north", "west"]
    ids = [prediction["id"] for prediction in report["predictions"]]
    assert ids == sorted(ids)
    decimals = re.findall(
        r'"(?:accuracy|macroF1|logLoss|confidence)": (-?\d+\.\d{6})(?=[,}])',
        raw,
    )
    assert len(decimals) == len(report["folds"]) + 3 + len(report["predictions"])


def test_seeded_generated_audits_match_independent_calculation(tmp_path):
    """Several generated ARFF datasets match an independent grouped evaluation."""
    rng = random.Random(20260725)
    for case in range(3):
        rows = []
        groups = ["site-z", "site-a", "site-m", "site-b"]
        for group_index, group in enumerate(groups):
            for class_index, label in enumerate(["low", "high"]):
                for repetition in range(2):
                    features = []
                    for feature in range(3):
                        value = (
                            class_index * (2.0 + feature)
                            + group_index * 0.35
                            + rng.uniform(-0.8, 0.8)
                        )
                        features.append(
                            None if rng.random() < 0.12 else round(value, 6)
                        )
                    rows.append(
                        {
                            "id": (
                                f"case-{case}-{group_index}-{class_index}-{repetition}"
                            ),
                            "group": group,
                            "features": features,
                            "class": label,
                        }
                    )
        case_dir = tmp_path / f"case-{case}"
        case_dir.mkdir()
        _assert_matches(case_dir, ["low", "high"], rows, top=2)


def test_invalid_data_removes_an_existing_report(tmp_path):
    """A data validation failure exits one and leaves no stale output report."""
    rows = _balanced_rows()
    rows[1]["id"] = rows[0]["id"]
    data_path = tmp_path / "duplicate.arff"
    output_path = tmp_path / "report.json"
    _write_arff(data_path, ["cold", "warm"], rows)
    output_path.write_text('{"stale": true}\n')

    result = _run(data_path, output_path, top=2)

    assert result.returncode == 1
    assert result.stderr.startswith("error: id values must be unique")
    assert not output_path.exists()


def test_invalid_top_values_remove_an_existing_report(tmp_path):
    """Out-of-range top counts exit one and leave no stale output report."""
    data_path = tmp_path / "valid.arff"
    _write_arff(data_path, ["cold", "warm"], _balanced_rows())
    for top in (0, 3):
        output_path = tmp_path / f"top-{top}.json"
        output_path.write_text('{"stale": true}\n', encoding="utf-8")
        result = _run(data_path, output_path, top=top)
        assert result.returncode == 1, (top, result.stderr)
        assert result.stderr.startswith("error: "), (top, result.stderr)
        assert not output_path.exists(), top


def test_invalid_arff_schemas_are_rejected(tmp_path):
    """Attribute types, predictor shape, group count, and fold coverage are validated."""
    cases = {
        "numeric-class": """
@relation bad
@attribute id string
@attribute group string
@attribute x numeric
@attribute outcome numeric
@data
'a','g1',0,0
'b','g2',1,1
""",
        "numeric-id": """
@relation bad
@attribute id numeric
@attribute group string
@attribute x numeric
@attribute outcome {a,b}
@data
1,'g1',0,a
2,'g1',1,b
3,'g2',0,a
4,'g2',1,b
""",
        "nominal-predictor": """
@relation bad
@attribute id string
@attribute group string
@attribute x {low,high}
@attribute outcome {a,b}
@data
'a','g1',low,a
'b','g1',high,b
'c','g2',low,a
'd','g2',high,b
""",
        "no-predictor": """
@relation bad
@attribute id string
@attribute group string
@attribute outcome {a,b}
@data
'a','g1',a
'b','g1',b
'c','g2',a
'd','g2',b
""",
        "one-group": """
@relation bad
@attribute id string
@attribute group string
@attribute x numeric
@attribute outcome {a,b}
@data
'a','g1',0,a
'b','g1',1,b
""",
        "missing-training-class": """
@relation bad
@attribute id string
@attribute group string
@attribute x numeric
@attribute outcome {a,b}
@data
'a','g1',0,a
'b','g1',1,a
'c','g2',2,b
'd','g2',3,b
""",
        "missing-group": """
@relation bad
@attribute id string
@attribute group string
@attribute x numeric
@attribute outcome {a,b}
@data
'a',?,0,a
'b','g1',1,b
'c','g2',0,a
'd','g2',1,b
""",
    }

    for name, source in cases.items():
        data_path = tmp_path / f"{name}.arff"
        output_path = tmp_path / f"{name}.json"
        data_path.write_text(source.strip() + "\n", encoding="utf-8")
        output_path.write_text('{"stale": true}\n', encoding="utf-8")
        result = _run(data_path, output_path, top=1)
        assert result.returncode == 1, (name, result.stderr)
        assert result.stderr.startswith("error: "), name
        assert not output_path.exists(), name

    valid_path = tmp_path / "valid.arff"
    _write_arff(valid_path, ["cold", "warm"], _balanced_rows())
    result = _run(
        valid_path,
        tmp_path / "missing-attribute.json",
        class_name="absent",
        top=2,
    )
    assert result.returncode == 1
    assert result.stderr.startswith("error: attribute not found: absent")
