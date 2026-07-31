"""Config-driven verifier for one R-KNN calibration task.

Three tiers, in order of what they hold the solver to:

  STRUCTURE            the contracted artifacts exist with the exact schemas, dtypes and
                       orderings from report_contract.csv; a fresh run is deterministic under
                       env overrides; the leakage counterfactuals hold (flipping fit labels
                       must move the held-out predictions, planting held-out labels must not).

  INTERNAL CONSISTENCY every derived report is an HONEST account of the solver's OWN model:
                       metrics, confusion, per-class scores, calibration bins, the group
                       report and the threshold sweep are recomputed from the solver's own
                       serialized per-row probabilities and predictions -- never from a pinned
                       reference recipe. The neighbour and leave-one-out audits, which cannot
                       be recomputed without pinning the recipe, are held to schema plus
                       self-consistency (valid references, ranked distances, weights summing
                       to one, thresholded labels, edges that tile the unit interval).

  QUALITY FLOORS       the difficulty core: the solver's held-out predictions must clear
                       min_accuracy and min_macro_f1 against the sealed labels. The floor is
                       calibrated (gen.py) at the well-executed oracle's held-out metric minus
                       a slack, and gen.py hard-fails unless a sloppy baseline falls clearly
                       below it -- so clearing the floor demands genuinely careful modelling,
                       not recipe replication. The floor test is named test_holdout_floor_holds
                       so the band verdict machinery reads a clean floor-miss.

Held-out truth and the quality floors are sealed under tests/eval/ and never enter the image.
Tolerances: 1e-5 on metrics, 2e-5 on probabilities (the R side serializes at 6 decimals).
"""
import csv
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/app/config"))
OUT_DIR = Path(os.environ.get("OUT_DIR", os.environ.get("OUTPUT_DIR", "/app/outputs")))
EVAL_DIR = Path(os.environ.get("EVAL_DIR", str(Path(__file__).resolve().parent / "eval")))
ANALYSIS = Path(os.environ.get("ANALYSIS_PATH", "/app/analysis.R"))

BLANK_TOKENS = ("", "NA", "NaN", "nan", "null", "?")
PROB_ATOL = 2e-5
METRIC_ATOL = 1e-5

CONTRACTED_ARTIFACTS = (
    "predictions.csv",
    "validation_predictions.csv",
    "metrics.json",
    "selection_report.csv",
    "threshold_report.csv",
    "confusion_matrix.csv",
    "class_metrics.csv",
    "calibration_bins.csv",
    "group_error_report.csv",
    "feature_summary.csv",
    "neighbor_evidence.csv",
    "fit_reference_calibration.csv",
    "neighbor_detail.csv",
    "loo_audit.csv",
)


# ---------------------------------------------------------------- plumbing

def load_rows(path):
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def load_header(path):
    with open(path, newline="") as handle:
        return next(csv.reader(handle))


def load_key_values(path):
    return {row["key"]: row["value"] for row in load_rows(path)}


def tidy_token(label):
    squashed = "".join(ch if ch.isalnum() else "_" for ch in label.lower())
    return squashed.strip("_")


def prob_columns(classes):
    return [f"prob_{tidy_token(cls)}" for cls in classes]


def macro_f1_score(actual, predicted, classes):
    per_class = []
    for cls in classes:
        tp = sum(1 for a, p in zip(actual, predicted) if a == cls and p == cls)
        fp = sum(1 for a, p in zip(actual, predicted) if a != cls and p == cls)
        fn = sum(1 for a, p in zip(actual, predicted) if a == cls and p != cls)
        precision = 0.0 if tp + fp == 0 else tp / (tp + fp)
        recall = 0.0 if tp + fn == 0 else tp / (tp + fn)
        per_class.append(0.0 if precision + recall == 0
                         else 2 * precision * recall / (precision + recall))
    return sum(per_class) / len(per_class)


def selected_flag(token):
    """The `selected` flag must be the integer digits 1/0, never TRUE/FALSE (same contract
    as `correct`/`loo_correct`). Reject anything else so a truthy TRUE/FALSE cannot pass."""
    value = str(token).strip()
    assert value in ("0", "1"), f"selected must be the integer digits 1/0, got {token!r}"
    return value == "1"


def run_analysis(data_dir, out_dir):
    env = os.environ.copy()
    env["DATA_DIR"] = str(data_dir)
    env["DATA_PATH"] = str(Path(data_dir) / DATA_FILE_NAME())
    env["OUT_DIR"] = str(out_dir)
    env["OUTPUT_DIR"] = str(out_dir)
    result = subprocess.run(
        ["Rscript", str(ANALYSIS)],
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def DATA_FILE_NAME():
    return load_key_values(CONFIG_DIR / "model_config.csv")["data_file"]


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def config():
    raw = load_key_values(CONFIG_DIR / "model_config.csv")
    costs = load_key_values(CONFIG_DIR / "costs.csv")
    raw["classes"] = raw["class_order"].split("|")
    raw["negative_class"] = next(c for c in raw["classes"] if c != raw["positive_class"])
    raw["k_values"] = [int(x) for x in raw["k_grid"].split("|")]
    raw["threshold_values"] = [float(x) for x in raw["threshold_grid"].split("|")]
    raw["fp_cost"] = float(costs["false_positive_cost"])
    raw["fn_cost"] = float(costs["false_negative_cost"])
    return raw


@pytest.fixture(scope="module")
def roles():
    return load_rows(CONFIG_DIR / "feature_roles.csv")


@pytest.fixture(scope="module")
def contract():
    return load_rows(CONFIG_DIR / "report_contract.csv")


@pytest.fixture(scope="module")
def table(config):
    return load_rows(DATA_DIR / config["data_file"])


@pytest.fixture(scope="session", autouse=True)
def sealed_truth():
    """Read the sealed held-out labels and quality floors into memory, then UNLINK them
    from disk before any graded solver RERUN. The determinism and leakage counterfactual
    tests rerun analysis.R; unlinking first guarantees no rerun can read the withheld truth
    off /tests/eval, while the parsed content lives only in this process's memory (never in
    an env var, so the reruns' os.environ copy cannot carry it either)."""
    labels = load_rows(EVAL_DIR / "test_labels.csv")
    floor_values = load_key_values(EVAL_DIR / "quality_floors.csv")
    for name in ("test_labels.csv", "quality_floors.csv"):
        try:
            (EVAL_DIR / name).unlink()
        except OSError:
            pass
    return {"labels": labels, "floors": floor_values}


@pytest.fixture(scope="module")
def sealed_labels(sealed_truth):
    return sealed_truth["labels"]


@pytest.fixture(scope="module")
def floors(sealed_truth):
    return sealed_truth["floors"]


@pytest.fixture
def protected_out_dir(tmp_path):
    """Snapshot the graded OUT_DIR and restore it after a rerun, so a solver that ignores
    the OUT_DIR override and writes to the real output dir cannot contaminate the graded
    artifacts that later tests re-read from OUT_DIR."""
    backup = tmp_path / "out_backup"
    shutil.copytree(OUT_DIR, backup)
    yield
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    shutil.copytree(backup, OUT_DIR)


@pytest.fixture(scope="module")
def predictions():
    return load_rows(OUT_DIR / "predictions.csv")


@pytest.fixture(scope="module")
def validation_predictions():
    return load_rows(OUT_DIR / "validation_predictions.csv")


@pytest.fixture(scope="module")
def metrics():
    return json.loads((OUT_DIR / "metrics.json").read_text())


def reference_ids(table, config):
    split_col = config["split_column"]
    return {int(r[config["id_column"]]) for r in table if r[split_col] in ("fit", "validation")}


# ================================================================ TIER 1: STRUCTURE

class TestStructure:
    def test_contracted_artifacts_exist(self):
        """Every artifact named in the report contract is present under the output dir."""
        missing = [name for name in CONTRACTED_ARTIFACTS if not (OUT_DIR / name).exists()]
        assert not missing, f"missing artifacts: {missing}"

    def test_artifact_schemas_match_contract(self, contract):
        """Each artifact's columns/keys match report_contract.csv exactly, in order."""
        listed = {row["artifact"] for row in contract}
        assert listed == set(CONTRACTED_ARTIFACTS), (sorted(listed), sorted(CONTRACTED_ARTIFACTS))
        for row in contract:
            name = row["artifact"]
            expected = row["columns"].split("|")
            path = OUT_DIR / name
            assert path.exists(), f"missing artifact {name}"
            if name.endswith(".json"):
                obj = json.loads(path.read_text())
                assert set(obj) == set(expected), (name, sorted(obj), sorted(expected))
            else:
                assert load_header(path) == expected, (name, load_header(path), expected)

    def test_public_test_targets_are_blank(self, table, config):
        """The public snapshot must not disclose the held-out labels."""
        leaked = [r for r in table
                  if r[config["split_column"]] == "test"
                  and r[config["target_column"]] not in BLANK_TOKENS]
        assert not leaked

    def test_feature_summary_recounts_missing_values(self, table, roles, config):
        """feature_summary.csv lists the configured features in order with true missing counts."""
        summary = load_rows(OUT_DIR / "feature_summary.csv")
        expected = [(r["feature"], r["data_type"]) for r in roles if r["role"] == "feature"]
        assert [(s["feature"], s["data_type"]) for s in summary] == expected
        split_col = config["split_column"]
        for entry in summary:
            for split, column in (("fit", "missing_fit"),
                                  ("validation", "missing_validation"),
                                  ("test", "missing_test")):
                count = sum(1 for r in table
                            if r[split_col] == split and r[entry["feature"]] in BLANK_TOKENS)
                assert int(entry[column]) == count

    def test_predictions_cover_sealed_rows(self, predictions, sealed_labels, config):
        """predictions.csv holds each held-out id exactly once, ascending."""
        id_col = config["id_column"]
        ids = [int(r[id_col]) for r in predictions]
        assert len(ids) == len(set(ids))
        assert set(ids) == {int(r[id_col]) for r in sealed_labels}
        assert ids == sorted(ids)

    def test_probability_rows_are_coherent(self, predictions, validation_predictions,
                                           metrics, table, config):
        """Probabilities are normalized and labels follow the operating threshold."""
        id_col = config["id_column"]
        group_col = config["group_column"]
        neg_col, pos_col = prob_columns(config["classes"])
        threshold = float(metrics["operating_threshold"])
        group_by_id = {r[id_col]: r[group_col] for r in table}
        for frame in (predictions, validation_predictions):
            for row in frame:
                p_neg = float(row[neg_col])
                p_pos = float(row[pos_col])
                assert 0.0 <= p_neg <= 1.0 and 0.0 <= p_pos <= 1.0
                assert abs(p_neg + p_pos - 1.0) <= 1e-4
                wanted = config["positive_class"] if p_pos >= threshold else config["negative_class"]
                assert row["pred_label"] == wanted
                assert row[group_col] == group_by_id[row[id_col]]

    def test_validation_rows_are_labeled_from_table(self, validation_predictions, table, config):
        """validation_predictions.csv restates the true validation labels and the correct flag."""
        id_col = config["id_column"]
        split_col = config["split_column"]
        target_col = config["target_column"]
        actual_by_id = {r[id_col]: r[target_col] for r in table if r[split_col] == "validation"}
        ids = [int(r[id_col]) for r in validation_predictions]
        assert ids == sorted(ids)
        assert {r[id_col] for r in validation_predictions} == set(actual_by_id)
        for row in validation_predictions:
            assert row["actual"] == actual_by_id[row[id_col]]
            assert int(row["correct"]) == int(row["actual"] == row["pred_label"])

    def test_rerun_is_deterministic(self, tmp_path, config, protected_out_dir):
        """A fresh run under DATA_DIR/OUT_DIR overrides reproduces EVERY contracted artifact
        byte-for-byte, not just predictions.csv."""
        clone = tmp_path / "data"
        shutil.copytree(DATA_DIR, clone)
        out = tmp_path / "out"
        out.mkdir()
        run_analysis(clone, out)
        for name in CONTRACTED_ARTIFACTS:
            assert (out / name).read_text() == (OUT_DIR / name).read_text(), name

    def test_fit_label_flip_moves_predictions(self, tmp_path, predictions, config,
                                              protected_out_dir):
        """Rotating the fit labels must change the held-out probabilities."""
        split_col = config["split_column"]
        target_col = config["target_column"]
        flip = {config["positive_class"]: config["negative_class"],
                config["negative_class"]: config["positive_class"]}

        def mutate(rows):
            for row in rows:
                if row[split_col] == "fit":
                    row[target_col] = flip[row[target_col]]

        rewrite_snapshot(DATA_DIR, tmp_path / "data", config["data_file"], mutate)
        out = tmp_path / "out"
        out.mkdir()
        run_analysis(tmp_path / "data", out)
        altered = load_rows(out / "predictions.csv")
        _, pos_col = prob_columns(config["classes"])
        id_col = config["id_column"]
        original = {r[id_col]: float(r[pos_col]) for r in predictions}
        drift = sum(abs(float(r[pos_col]) - original[r[id_col]]) for r in altered)
        assert drift / len(altered) > 1e-6

    def test_injected_test_labels_change_nothing(self, tmp_path, predictions, config,
                                                 protected_out_dir):
        """Planted labels on held-out rows must not leak into the predictions."""
        split_col = config["split_column"]
        target_col = config["target_column"]
        classes = config["classes"]

        def mutate(rows):
            planted = 0
            for row in rows:
                if row[split_col] == "test":
                    row[target_col] = classes[planted % len(classes)]
                    planted += 1

        rewrite_snapshot(DATA_DIR, tmp_path / "data", config["data_file"], mutate)
        out = tmp_path / "out"
        out.mkdir()
        run_analysis(tmp_path / "data", out)
        altered = load_rows(out / "predictions.csv")
        id_col = config["id_column"]
        neg_col, pos_col = prob_columns(classes)
        original = {r[id_col]: r for r in predictions}
        assert [r[id_col] for r in altered] == [r[id_col] for r in predictions]
        for row in altered:
            baseline = original[row[id_col]]
            assert row["pred_label"] == baseline["pred_label"]
            assert abs(float(row[pos_col]) - float(baseline[pos_col])) <= PROB_ATOL
            assert abs(float(row[neg_col]) - float(baseline[neg_col])) <= PROB_ATOL


def rewrite_snapshot(source_dir, target_dir, data_file, mutate):
    shutil.copytree(source_dir, target_dir)
    path = Path(target_dir) / data_file
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    mutate(rows)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ================================================================ TIER 2: INTERNAL CONSISTENCY

class TestInternalConsistency:
    def test_metrics_summarize_own_validation(self, validation_predictions, metrics, table, config):
        """metrics.json is an honest summary of the serialized validation table."""
        actual = [r["actual"] for r in validation_predictions]
        labels = [r["pred_label"] for r in validation_predictions]
        accuracy = sum(1 for a, p in zip(actual, labels) if a == p) / len(actual)
        f1 = macro_f1_score(actual, labels, config["classes"])
        assert abs(float(metrics["validation_accuracy"]) - accuracy) <= METRIC_ATOL
        assert abs(float(metrics["validation_macro_f1"]) - f1) <= METRIC_ATOL
        threshold = float(metrics["operating_threshold"])
        assert any(abs(threshold - t) <= 1e-9 for t in config["threshold_values"])
        assert int(metrics["selected_k"]) in config["k_values"]
        _, pos_col = prob_columns(config["classes"])
        fp = sum(1 for r in validation_predictions
                 if r["actual"] == config["negative_class"] and float(r[pos_col]) >= threshold)
        fn = sum(1 for r in validation_predictions
                 if r["actual"] == config["positive_class"] and float(r[pos_col]) < threshold)
        cost = (config["fp_cost"] * fp + config["fn_cost"] * fn) / len(validation_predictions)
        assert abs(float(metrics["validation_expected_cost"]) - cost) <= METRIC_ATOL
        split_col = config["split_column"]
        for split, key in (("fit", "n_fit"), ("validation", "n_validation"), ("test", "n_test")):
            assert int(metrics[key]) == sum(1 for r in table if r[split_col] == split)
        assert metrics["task_kind"] == config["task_kind"]
        assert metrics["target_column"] == config["target_column"]

    def test_selection_report_is_self_consistent(self, metrics, config):
        """selection_report.csv sweeps the k grid in order and names one selected k."""
        report = load_rows(OUT_DIR / "selection_report.csv")
        assert [int(r["candidate_k"]) for r in report] == config["k_values"]
        for row in report:
            score = float(row["validation_macro_f1"])
            assert 0.0 <= score <= 1.0
        chosen = [r for r in report if selected_flag(r["selected"])]
        assert len(chosen) == 1
        assert int(chosen[0]["candidate_k"]) == int(metrics["selected_k"])
        assert int(metrics["selected_k"]) in config["k_values"]

    def test_threshold_report_is_self_consistent(self, validation_predictions, metrics, config):
        """threshold_report.csv restates both cost sweeps over the solver's own validation probs.

        The per-threshold counts, expected cost and worst-group cost must match a recompute
        from the serialized validation probabilities; exactly one row is selected and it is
        the operating threshold in metrics.json. Which selection rule the solver used is NOT
        asserted -- the report only has to be an honest account of its own model.
        """
        report = load_rows(OUT_DIR / "threshold_report.csv")
        grid = config["threshold_values"]
        listed = [float(r["threshold"]) for r in report]
        assert len(listed) == len(grid)
        assert all(abs(a - b) <= 1e-9 for a, b in zip(listed, grid))
        _, pos_col = prob_columns(config["classes"])
        group_col = config["group_column"]
        pairs = [(r["actual"], float(r[pos_col]), r[group_col]) for r in validation_predictions]
        groups = sorted({g for _, _, g in pairs})
        for row, threshold in zip(report, grid):
            fp = sum(1 for actual, p, _ in pairs
                     if actual == config["negative_class"] and p >= threshold)
            fn = sum(1 for actual, p, _ in pairs
                     if actual == config["positive_class"] and p < threshold)
            cost = (config["fp_cost"] * fp + config["fn_cost"] * fn) / len(pairs)
            worst = -math.inf
            for name in groups:
                members = [(a, p) for a, p, g in pairs if g == name]
                gfp = sum(1 for a, p in members
                          if a == config["negative_class"] and p >= threshold)
                gfn = sum(1 for a, p in members
                          if a == config["positive_class"] and p < threshold)
                worst = max(worst,
                            (config["fp_cost"] * gfp + config["fn_cost"] * gfn) / len(members))
            assert int(row["false_positives"]) == fp
            assert int(row["false_negatives"]) == fn
            assert abs(float(row["expected_cost"]) - cost) <= METRIC_ATOL
            assert abs(float(row["worst_group_cost"]) - worst) <= METRIC_ATOL
        chosen = [r for r in report if selected_flag(r["selected"])]
        assert len(chosen) == 1
        assert abs(float(chosen[0]["threshold"]) - float(metrics["operating_threshold"])) <= 1e-9

    def test_classification_tables_restate_own_validation(self, validation_predictions, config):
        """Confusion matrix and per-class metrics restate the serialized validation table."""
        actual = [r["actual"] for r in validation_predictions]
        labels = [r["pred_label"] for r in validation_predictions]
        confusion = load_rows(OUT_DIR / "confusion_matrix.csv")
        expected_pairs = [(a, p) for a in config["classes"] for p in config["classes"]]
        assert [(r["actual"], r["predicted"]) for r in confusion] == expected_pairs
        for row in confusion:
            count = sum(1 for a, p in zip(actual, labels)
                        if a == row["actual"] and p == row["predicted"])
            assert int(row["count"]) == count
        per_class = load_rows(OUT_DIR / "class_metrics.csv")
        assert [r["class"] for r in per_class] == config["classes"]
        for row in per_class:
            cls = row["class"]
            tp = sum(1 for a, p in zip(actual, labels) if a == cls and p == cls)
            fp = sum(1 for a, p in zip(actual, labels) if a != cls and p == cls)
            fn = sum(1 for a, p in zip(actual, labels) if a == cls and p != cls)
            precision = 0.0 if tp + fp == 0 else tp / (tp + fp)
            recall = 0.0 if tp + fn == 0 else tp / (tp + fn)
            f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
            assert abs(float(row["precision"]) - precision) <= METRIC_ATOL
            assert abs(float(row["recall"]) - recall) <= METRIC_ATOL
            assert abs(float(row["f1"]) - f1) <= METRIC_ATOL
            assert int(row["support"]) == sum(1 for a in actual if a == cls)

    def test_calibration_and_group_tables_restate_own_validation(self, validation_predictions, config):
        """Calibration bins and the group report restate the serialized validation table."""
        _, pos_col = prob_columns(config["classes"])
        rows = [(float(r[pos_col]), r["actual"], r[config["group_column"]],
                 r["pred_label"]) for r in validation_predictions]
        bins = load_rows(OUT_DIR / "calibration_bins.csv")
        assert len(bins) == 5
        for index, row in enumerate(bins):
            assert abs(float(row["bin_low"]) - index / 5) <= 1e-9
            assert abs(float(row["bin_high"]) - (index + 1) / 5) <= 1e-9
            members = [(p, a) for p, a, _, _ in rows if min(4, int(p * 5)) == index]
            assert int(row["count"]) == len(members)
            if members:
                mean_p = sum(p for p, _ in members) / len(members)
                observed = sum(1 for _, a in members
                               if a == config["positive_class"]) / len(members)
            else:
                mean_p = 0.0
                observed = 0.0
            assert abs(float(row["mean_predicted"]) - mean_p) <= METRIC_ATOL
            assert abs(float(row["observed_rate"]) - observed) <= METRIC_ATOL
        report = load_rows(OUT_DIR / "group_error_report.csv")
        groups = sorted({g for _, _, g, _ in rows})
        assert [r["group_value"] for r in report] == groups
        for row in report:
            members = [(a, lab) for _, a, g, lab in rows if g == row["group_value"]]
            assert int(row["n_validation"]) == len(members)
            accuracy = sum(1 for a, lab in members if a == lab) / len(members)
            assert abs(float(row["accuracy"]) - accuracy) <= METRIC_ATOL

    def test_neighbor_evidence_is_self_consistent(self, predictions, table, config):
        """neighbor_evidence.csv lists the first held-out ids with a valid nearest reference."""
        report = load_rows(OUT_DIR / "neighbor_evidence.csv")
        id_col = config["id_column"]
        held_out = sorted(int(r[id_col]) for r in predictions)
        assert [int(r[id_col]) for r in report] == held_out[:50]
        refs = reference_ids(table, config)
        for row in report:
            assert int(row["nearest_reference_id"]) in refs
            assert float(row["nearest_distance"]) >= 0.0

    def test_fit_reference_calibration_is_self_consistent(self, validation_predictions, config):
        """The bins tile [0, 1] and honestly bin the solver's own validation probabilities."""
        report = load_rows(OUT_DIR / "fit_reference_calibration.csv")
        assert [int(r["bin"]) for r in report] == [1, 2, 3, 4, 5]
        lowers = [float(r["lower_edge"]) for r in report]
        uppers = [float(r["upper_edge"]) for r in report]
        assert abs(lowers[0]) <= 1e-9
        assert abs(uppers[4] - 1.0) <= 1e-9
        for i in range(5):
            assert lowers[i] <= uppers[i] + 1e-9
        for i in range(4):
            assert uppers[i] <= uppers[i + 1] + 1e-9
            assert abs(uppers[i] - lowers[i + 1]) <= 1e-9
        _, pos_col = prob_columns(config["classes"])
        edges = uppers[:4]
        rows = [(float(r[pos_col]), r["actual"]) for r in validation_predictions]
        for index, row in enumerate(report):
            members = [(p, a) for p, a in rows if sum(1 for e in edges if e < p) == index]
            assert int(row["count"]) == len(members)
            if members:
                mean_p = sum(p for p, _ in members) / len(members)
                observed = sum(1 for _, a in members
                               if a == config["positive_class"]) / len(members)
            else:
                mean_p = 0.0
                observed = 0.0
            assert abs(float(row["mean_predicted"]) - mean_p) <= METRIC_ATOL
            assert abs(float(row["observed_rate"]) - observed) <= METRIC_ATOL

    def test_neighbor_detail_is_self_consistent(self, predictions, metrics, table, config):
        """Per held-out row: selected-k distinct references, ranked by distance, weights to one."""
        report = load_rows(OUT_DIR / "neighbor_detail.csv")
        id_col = config["id_column"]
        held_out = sorted(int(r[id_col]) for r in predictions)[:40]
        per_id = {}
        for row in report:
            per_id.setdefault(int(row[id_col]), []).append(row)
        assert sorted(per_id) == held_out
        refs = reference_ids(table, config)
        detail_k = min(int(metrics["selected_k"]), len(refs))
        for tid in held_out:
            rows = per_id[tid]
            assert [int(r["neighbor_rank"]) for r in rows] == list(range(1, detail_k + 1))
            neighbor_ids = [int(r["neighbor_id"]) for r in rows]
            assert len(set(neighbor_ids)) == len(neighbor_ids)
            assert all(nid in refs for nid in neighbor_ids)
            distances = [float(r["distance"]) for r in rows]
            assert all(d >= 0.0 for d in distances)
            assert distances == sorted(distances)
            shares = [float(r["weight_share"]) for r in rows]
            assert all(0.0 <= s <= 1.0 for s in shares)
            assert abs(sum(shares) - 1.0) <= 1e-4

    def test_loo_audit_is_self_consistent(self, metrics, table, config):
        """The designated fit rows carry probabilities in [0,1] labeled at the threshold."""
        report = load_rows(OUT_DIR / "loo_audit.csv")
        id_col = config["id_column"]
        split_col = config["split_column"]
        target_col = config["target_column"]
        fit_rows = [r for r in table if r[split_col] == "fit"]
        n_fit = len(fit_rows)
        stride = max(1, n_fit // 12)
        fit_ids_sorted = sorted(int(r[id_col]) for r in fit_rows)
        expected_ids = [fit_ids_sorted[j * stride] for j in range(12) if j * stride < n_fit]
        assert [int(r[id_col]) for r in report] == expected_ids
        actual_by_id = {int(r[id_col]): r[target_col] for r in fit_rows}
        threshold = float(metrics["operating_threshold"])
        for row in report:
            rid = int(row[id_col])
            assert row["actual"] == actual_by_id[rid]
            prob = float(row["loo_positive_prob"])
            assert 0.0 <= prob <= 1.0
            wanted = (config["positive_class"] if prob >= threshold
                      else config["negative_class"])
            assert row["loo_pred_label"] == wanted
            assert int(row["loo_correct"]) == int(row["loo_pred_label"] == row["actual"])


# ================================================================ TIER 3: QUALITY FLOORS

class TestQualityFloors:
    def test_holdout_floor_holds(self, predictions, sealed_labels, floors, config):
        """The sealed held-out labels score above the calibrated quality floors."""
        id_col = config["id_column"]
        truth = {r[id_col]: r[config["target_column"]] for r in sealed_labels}
        actual = [truth[r[id_col]] for r in predictions]
        labels = [r["pred_label"] for r in predictions]
        accuracy = sum(1 for a, p in zip(actual, labels) if a == p) / len(actual)
        f1 = macro_f1_score(actual, labels, config["classes"])
        assert accuracy >= float(floors["min_accuracy"])
        assert f1 >= float(floors["min_macro_f1"])
