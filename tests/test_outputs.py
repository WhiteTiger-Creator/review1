"""Independent checks for the teaching-evaluation multiclass artifacts."""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import f1_score

OUT = Path("/app/outputs")
EXPECTED = Path("/tests/expected")
DATA = Path("/app/data")
EVAL = Path(os.environ.get("VERIFIER_EVAL_DIR", "/tests/eval"))
CLASSES = ["eval_low", "eval_medium", "eval_high"]
FEATURES = [
    "native_english_speaker",
    "course_instructor",
    "course_id",
    "summer_or_regular",
    "class_size",
]
C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0]
ARTIFACTS = [
    "metrics.json",
    "candidate_results.csv",
    "fit_cv_results.csv",
    "fit_oof_predictions.csv",
    "fold_preprocessing_summary.csv",
    "predictions.csv",
    "validation_confusion_matrix.csv",
    "validation_class_report.csv",
    "validation_confidence_deciles.csv",
    "score_course_counterfactual.csv",
    "model_term_importance.csv",
    "preprocessing_summary.csv",
    "model_manifest.json",
]


def read_json(directory: Path, name: str) -> dict:
    """Load one JSON artifact."""
    return json.loads((directory / name).read_text(encoding="utf-8"))


def read_csv(directory: Path, name: str) -> pd.DataFrame:
    """Load one CSV artifact."""
    return pd.read_csv(directory / name)


def assert_json_close(observed: object, expected: object) -> None:
    """Compare nested JSON with public-precision tolerance."""
    if isinstance(expected, dict):
        assert isinstance(observed, dict)
        assert list(observed) == list(expected)
        for key in expected:
            assert_json_close(observed[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(observed, list)
        assert len(observed) == len(expected)
        for observed_item, expected_item in zip(observed, expected, strict=True):
            assert_json_close(observed_item, expected_item)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert float(observed) == pytest.approx(float(expected), abs=2e-6)
    else:
        assert str(observed) == str(expected)


def assert_frame_close(observed: pd.DataFrame, expected: pd.DataFrame) -> None:
    """Compare CSV structure and values at published precision."""
    assert list(observed.columns) == list(expected.columns)
    assert observed.shape == expected.shape
    for column in expected.columns:
        if pd.api.types.is_numeric_dtype(expected[column]):
            assert np.allclose(
                pd.to_numeric(observed[column]),
                pd.to_numeric(expected[column]),
                atol=2e-6,
                rtol=0,
                equal_nan=True,
            )
        else:
            assert observed[column].astype(str).tolist() == expected[
                column
            ].astype(str).tolist()


def assign_folds(frame: pd.DataFrame) -> dict[str, int]:
    """Rebuild the published class-stratified folds."""
    assigned: dict[str, int] = {}
    for label in CLASSES:
        rows = frame.loc[frame["evaluation_class"] == label].sort_values("row_id")
        for position, row_id in enumerate(rows["row_id"].astype(str), start=1):
            assigned[row_id] = ((position - 1) % 5) + 1
    return assigned


def multiclass_metrics(
    actual: pd.Series, probabilities: np.ndarray
) -> tuple[float, float, float]:
    """Compute macro F1, accuracy, and natural-log loss."""
    predicted = np.asarray(CLASSES)[np.argmax(probabilities, axis=1)]
    macro = f1_score(actual, predicted, labels=CLASSES, average="macro")
    accuracy = float(np.mean(predicted == actual.to_numpy()))
    class_positions = {label: index for index, label in enumerate(CLASSES)}
    selected = np.asarray(
        [
            probabilities[row_index, class_positions[label]]
            for row_index, label in enumerate(actual.astype(str))
        ]
    )
    loss = float(np.mean(-np.log(np.clip(selected, 1e-15, 1.0))))
    return float(macro), accuracy, float(loss)


def test_exact_artifact_set_and_sealed_outputs() -> None:
    """Require all thirteen files and compare with sealed evidence."""
    assert sorted(path.name for path in OUT.iterdir()) == sorted(ARTIFACTS)
    assert sorted(path.name for path in EXPECTED.iterdir()) == sorted(ARTIFACTS)
    for name in ["metrics.json", "model_manifest.json"]:
        assert_json_close(read_json(OUT, name), read_json(EXPECTED, name))
    for name in [item for item in ARTIFACTS if item.endswith(".csv")]:
        assert_frame_close(read_csv(OUT, name), read_csv(EXPECTED, name))


def test_manifest_declares_public_scope_and_pipeline() -> None:
    """Validate input scope, model metadata, and artifact declaration."""
    manifest = read_json(OUT, "model_manifest.json")
    train = pd.read_csv(DATA / "train.csv")
    score = pd.read_csv(DATA / "score.csv")
    assert manifest["feature_columns"] == FEATURES
    assert manifest["categorical_columns"] == FEATURES[:4]
    assert manifest["numeric_columns"] == ["class_size"]
    assert manifest["excluded_columns"] == [
        "row_id",
        "split_role",
        "evaluation_class",
    ]
    assert manifest["class_order"] == CLASSES
    assert [float(value) for value in manifest["candidate_grid"]] == C_GRID
    assert manifest["artifact_files"] == ARTIFACTS
    assert manifest["fit_rows"] == int((train["split_role"] == "fit").sum())
    assert manifest["validation_rows"] == int(
        (train["split_role"] == "validation").sum()
    )
    assert manifest["score_rows"] == len(score)
    assert len(manifest["design_columns"]) > len(FEATURES)


def test_candidate_path_varies_and_selects_cv_minimum() -> None:
    """Ensure regularization changes behavior and selection follows CV loss."""
    candidates = read_csv(OUT, "candidate_results.csv")
    assert candidates["candidate_c"].astype(float).tolist() == C_GRID
    assert candidates["is_selected"].astype(int).sum() == 1
    assert candidates["cv_mean_log_loss"].nunique() > 3
    selected = candidates.loc[candidates["is_selected"] == 1].iloc[0]
    minimum = candidates["cv_mean_log_loss"].min()
    assert float(selected["cv_mean_log_loss"]) <= float(minimum) + 2e-6
    tied = candidates.loc[
        candidates["cv_mean_log_loss"] <= float(minimum) + 2e-6,
        "candidate_c",
    ]
    assert float(selected["candidate_c"]) == float(tied.min())


def test_cv_rows_cover_every_candidate_and_fold() -> None:
    """Reconcile candidate summaries with forty fold evaluations."""
    cv = read_csv(OUT, "fit_cv_results.csv")
    assert len(cv) == len(C_GRID) * 5
    assert cv[["candidate_c", "fold_id"]].drop_duplicates().shape[0] == len(cv)
    assert sorted(cv["fold_id"].astype(int).unique()) == [1, 2, 3, 4, 5]
    for c_value in C_GRID:
        rows = cv[np.isclose(cv["candidate_c"], c_value)]
        assert rows["fold_id"].astype(int).tolist() == [1, 2, 3, 4, 5]
        assert (rows["training_rows"] + rows["holdout_rows"]).nunique() == 1


def test_oof_predictions_cover_fit_rows_and_reconcile_metrics() -> None:
    """Check leakage-free OOF row coverage, folds, labels, and metrics."""
    train = pd.read_csv(DATA / "train.csv", dtype={"row_id": str})
    fit = train.loc[train["split_role"] == "fit"].copy()
    oof = read_csv(OUT, "fit_oof_predictions.csv")
    assert oof["row_id"].astype(str).tolist() == sorted(fit["row_id"].astype(str))
    expected_folds = assign_folds(fit)
    assert oof["fold_id"].astype(int).tolist() == [
        expected_folds[row_id] for row_id in oof["row_id"].astype(str)
    ]
    probabilities = oof[
        ["prob_eval_low", "prob_eval_medium", "prob_eval_high"]
    ].to_numpy(float)
    assert np.allclose(probabilities.sum(axis=1), 1, atol=2e-7)
    macro, _, loss = multiclass_metrics(
        oof["actual_class"].astype(str), probabilities
    )
    metrics = read_json(OUT, "metrics.json")
    assert macro == pytest.approx(metrics["fit_oof_macro_f1"], abs=2e-6)
    assert loss == pytest.approx(metrics["fit_oof_log_loss"], abs=2e-6)


def test_fold_preprocessing_is_fit_partition_local() -> None:
    """Independently reconstruct selected-fold numeric and level summaries."""
    train = pd.read_csv(DATA / "train.csv", dtype={"row_id": str})
    fit = train.loc[train["split_role"] == "fit"].copy()
    folds = assign_folds(fit)
    summary = read_csv(OUT, "fold_preprocessing_summary.csv")
    assert summary["fold_id"].astype(int).tolist() == [1, 2, 3, 4, 5]
    for _, row in summary.iterrows():
        fold = int(row["fold_id"])
        training = fit.loc[
            [folds[row_id] != fold for row_id in fit["row_id"].astype(str)]
        ]
        numeric = pd.to_numeric(training["class_size"], errors="coerce")
        center = float(numeric.mean()) if numeric.notna().any() else 0.0
        imputed = numeric.fillna(center)
        scale = float(imputed.std(ddof=1))
        if not np.isfinite(scale) or scale == 0:
            scale = 1.0
        instructors = set(training["course_instructor"].dropna().astype(str))
        courses = set(training["course_id"].dropna().astype(str))
        assert float(row["class_size_center"]) == pytest.approx(center, abs=2e-7)
        assert float(row["class_size_sample_sd"]) == pytest.approx(scale, abs=2e-7)
        assert int(row["instructor_level_count"]) == len(
            instructors | {"__missing__", "__other__"}
        )
        assert int(row["course_level_count"]) == len(
            courses | {"__missing__", "__other__"}
        )


def test_predictions_are_score_only_valid_and_nonconstant() -> None:
    """Validate score scope, class probabilities, and nondegenerate labels."""
    score = pd.read_csv(DATA / "score.csv", dtype={"row_id": str})
    predictions = read_csv(OUT, "predictions.csv")
    assert predictions["row_id"].astype(str).tolist() == sorted(score["row_id"])
    probabilities = predictions[
        ["prob_eval_low", "prob_eval_medium", "prob_eval_high"]
    ].to_numpy(float)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    assert np.allclose(probabilities.sum(axis=1), 1, atol=2e-7)
    expected_labels = np.asarray(CLASSES)[np.argmax(probabilities, axis=1)]
    assert predictions["predicted_class"].astype(str).tolist() == expected_labels.tolist()
    assert predictions["predicted_class"].nunique() >= 2


def test_validation_metrics_confusion_and_report_reconcile() -> None:
    """Reconcile validation metrics, confusion counts, and class summaries."""
    expected_cases = read_csv(EXPECTED, "validation_class_report.csv")
    report = read_csv(OUT, "validation_class_report.csv")
    assert_frame_close(report, expected_cases)
    confusion = read_csv(OUT, "validation_confusion_matrix.csv")
    train = pd.read_csv(DATA / "train.csv")
    validation = train.loc[train["split_role"] == "validation"]
    assert len(confusion) == 9
    assert confusion["n"].astype(int).sum() == len(validation)
    assert confusion["actual_class"].astype(str).tolist() == [
        actual for actual in CLASSES for _ in CLASSES
    ]
    assert confusion["predicted_class"].astype(str).tolist() == CLASSES * 3
    assert report["support"].astype(int).sum() == len(validation)
    metrics = read_json(OUT, "metrics.json")
    assert 0 <= float(metrics["validation_macro_f1"]) <= 1
    assert 0 <= float(metrics["validation_accuracy"]) <= 1
    assert float(metrics["validation_log_loss"]) > 0


def test_validation_confidence_deciles_cover_rows() -> None:
    """Require deterministic complete confidence-decile aggregation."""
    deciles = read_csv(OUT, "validation_confidence_deciles.csv")
    train = pd.read_csv(DATA / "train.csv")
    validation_rows = int((train["split_role"] == "validation").sum())
    assert deciles["decile"].astype(int).tolist() == list(range(1, 11))
    assert deciles["row_count"].astype(int).sum() == validation_rows
    assert deciles["accuracy"].between(0, 1).all()
    assert deciles["mean_confidence"].between(0, 1).all()
    assert deciles["mean_margin"].between(0, 1).all()


def test_course_counterfactual_is_complete_and_substantive() -> None:
    """Check course-instructor stress rows, class totals, and probability shifts."""
    counterfactual = read_csv(OUT, "score_course_counterfactual.csv")
    manifest = read_json(OUT, "model_manifest.json")
    score_rows = int(manifest["score_rows"])
    expected_levels = sorted(
        {
            column.removeprefix("course_instructor_")
            for column in manifest["design_columns"]
            if column.startswith("course_instructor_")
        }
    )
    assert len(counterfactual) == len(expected_levels)
    count_columns = [
        "predicted_eval_low_count",
        "predicted_eval_medium_count",
        "predicted_eval_high_count",
    ]
    assert (counterfactual[count_columns].sum(axis=1) == score_rows).all()
    means = counterfactual[
        ["mean_prob_eval_low", "mean_prob_eval_medium", "mean_prob_eval_high"]
    ].sum(axis=1)
    assert np.allclose(means, 1, atol=3e-6)
    assert counterfactual["mean_total_variation"].max() > 0


def test_model_term_importance_covers_features_and_normalizes() -> None:
    """Validate original-feature grouping and normalized coefficient magnitude."""
    importance = read_csv(OUT, "model_term_importance.csv")
    assert importance["feature"].astype(str).tolist() == FEATURES
    assert (importance["design_term_count"] > 0).all()
    assert (importance["l2_norm"] >= 0).all()
    assert float(importance["normalized_importance"].sum()) == pytest.approx(
        1.0, abs=5e-8
    )
    assert importance["l2_norm"].nunique() > 2


def test_preprocessing_summary_covers_features() -> None:
    """Check final-fit preprocessing scopes and feature typing."""
    summary = read_csv(OUT, "preprocessing_summary.csv")
    assert summary["feature"].astype(str).tolist() == FEATURES
    assert summary["feature_type"].astype(str).tolist() == [
        "categorical",
        "categorical",
        "categorical",
        "categorical",
        "numeric",
    ]
    assert (summary[["fit_missing_count", "validation_missing_count"]] >= 0).all().all()
    assert float(summary.iloc[-1]["fit_sample_sd"]) > 0


def test_hidden_score_quality_is_nontrivial() -> None:
    """Require useful but imperfect predictions on held-out score labels."""
    labels = pd.read_csv(EVAL / "labels.csv", dtype={"row_id": str})
    predictions = read_csv(OUT, "predictions.csv")
    merged = predictions.merge(labels, on="row_id", validate="one_to_one")
    accuracy = float(
        np.mean(
            merged["predicted_class"].astype(str)
            == merged["evaluation_class"].astype(str)
        )
    )
    assert 0.25 <= accuracy < 1.0
