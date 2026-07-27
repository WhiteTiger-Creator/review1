import csv
import math
import os
import shutil
import subprocess
import tempfile
from functools import cache

FIELDS = ["record_id", *[f"p_{digit}" for digit in range(10)]]
HIDDEN_SOURCE = "/tests/hidden_digit_labels.csv"
HIDDEN_DIR = "/tmp/pendigit-verifier"
HIDDEN_PATH = os.path.join(HIDDEN_DIR, "hidden_digit_labels.csv")


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def protect_verifier_files():
    if not os.path.exists(HIDDEN_PATH):
        os.makedirs(HIDDEN_DIR, mode=0o700, exist_ok=True)
        shutil.copyfile(HIDDEN_SOURCE, HIDDEN_PATH)
        os.chmod(HIDDEN_DIR, 0o700)
        os.chmod(HIDDEN_PATH, 0o600)
        try:
            os.remove(HIDDEN_SOURCE)
        except OSError:
            os.chmod(HIDDEN_SOURCE, 0o600)
    probe = subprocess.run(
        [
            "/usr/bin/setpriv",
            "--reuid=65534",
            "--regid=65534",
            "--clear-groups",
            "--no-new-privs",
            "/bin/sh",
            "-c",
            f"test ! -r {HIDDEN_PATH} && test ! -e {HIDDEN_SOURCE}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr


def run_candidate(input_dir="/app/data"):
    output_dir = tempfile.mkdtemp(prefix="pendigit-output-")
    os.chmod(output_dir, 0o777)
    result = subprocess.run(
        [
            "/usr/bin/setpriv",
            "--reuid=65534",
            "--regid=65534",
            "--clear-groups",
            "--no-new-privs",
            "/app/run.sh",
            input_dir,
            output_dir,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output_path = os.path.join(output_dir, "digit_probabilities.csv")
    assert os.path.isfile(output_path)
    return read_rows(output_path)


def load_scored(input_dir="/app/data"):
    predictions = run_candidate(input_dir)
    contexts = {
        row["record_id"]: row
        for row in read_rows(os.path.join(input_dir, "evaluation_digits.csv"))
    }
    hidden = {row["record_id"]: row for row in read_rows(HIDDEN_PATH)}
    assert len(hidden) >= 60
    assert predictions
    assert list(predictions[0]) == FIELDS
    assert len(predictions) == len(contexts) == len(hidden)
    assert len({row["record_id"] for row in predictions}) == len(predictions)
    assert {row["record_id"] for row in predictions} == set(contexts)
    scored = []
    for row in predictions:
        probabilities = [float(row[f"p_{digit}"]) for digit in range(10)]
        assert all(
            math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities
        )
        assert abs(sum(probabilities) - 1.0) <= 1e-6
        record_id = row["record_id"]
        context = contexts[record_id]
        target = hidden[record_id]
        scored.append(
            (
                record_id,
                probabilities,
                int(target["digit_label"]),
                float(context["policy_weight"]),
                float(context["behavior_propensity"]),
                context["capture_action"],
            )
        )
    return scored


@cache
def scored():
    protect_verifier_files()
    return load_scored()


def log_loss(rows):
    total = sum(row[3] for row in rows)
    return -sum(row[3] * math.log(max(row[1][row[2]], 1e-15)) for row in rows) / total


def macro_recall(rows, digits=None):
    if digits is None:
        digits = range(10)
    recalls = []
    for digit in digits:
        part = [row for row in rows if row[2] == digit]
        assert part
        recalls.append(
            sum(
                max(range(10), key=lambda index: (row[1][index], -index)) == digit
                for row in part
            )
            / len(part)
        )
    return sum(recalls) / len(recalls)


def brier_score(rows):
    total = sum(row[3] for row in rows)
    return (
        sum(
            row[3]
            * sum(
                (row[1][digit] - (1.0 if row[2] == digit else 0.0)) ** 2
                for digit in range(10)
            )
            for row in rows
        )
        / total
    )


def test_writer_independent_digit_quality():
    """Weighted probabilities identify digits in the writer-independent split."""
    rows = scored()
    assert log_loss(rows) < 0.140, f"log_loss={log_loss(rows)}"
    assert macro_recall(rows) > 0.955, f"macro_recall={macro_recall(rows)}"
    assert brier_score(rows) < 0.060, f"brier={brier_score(rows)}"


def test_low_behavior_capture_quality():
    """Low-behavior-propensity capture rows retain useful digit probabilities."""
    rows = [row for row in scored() if row[4] <= 0.4]
    assert len(rows) >= 1800
    assert log_loss(rows) < 0.100, f"low_behavior_log_loss={log_loss(rows)}"
    assert macro_recall(rows) > 0.965, f"low_behavior_macro_recall={macro_recall(rows)}"
    assert brier_score(rows) < 0.035, f"low_behavior_brier={brier_score(rows)}"


def test_compact_trace_generalization():
    """Compact-trace capture rows need accurate calibrated probabilities."""
    rows = [row for row in scored() if row[5] == "compact_trace"]
    assert len(rows) >= 1600
    assert log_loss(rows) < 0.180, f"compact_log_loss={log_loss(rows)}"
    assert macro_recall(rows) > 0.930, f"compact_macro_recall={macro_recall(rows)}"
    assert brier_score(rows) < 0.080, f"compact_brier={brier_score(rows)}"


def test_confusable_digit_policy_quality():
    """Digits with similar stroke geometry remain calibrated under the target policy."""
    digits = (1, 5, 7, 9)
    rows = [row for row in scored() if row[2] in digits]
    assert len(rows) >= 1300
    assert log_loss(rows) < 0.170, f"confusable_log_loss={log_loss(rows)}"
    assert macro_recall(rows, digits) > 0.935, (
        f"confusable_macro_recall={macro_recall(rows, digits)}"
    )
    assert brier_score(rows) < 0.075, f"confusable_brier={brier_score(rows)}"
    compact_rows = [row for row in rows if row[5] == "compact_trace"]
    assert len(compact_rows) >= 650
    assert log_loss(compact_rows) < 0.245, (
        f"compact_confusable_log_loss={log_loss(compact_rows)}"
    )
    assert macro_recall(compact_rows, digits) > 0.905, (
        f"compact_confusable_macro_recall={macro_recall(compact_rows, digits)}"
    )
    assert brier_score(compact_rows) < 0.110, (
        f"compact_confusable_brier={brier_score(compact_rows)}"
    )


def test_predictions_are_not_prior_templates():
    """Predicted digit distributions vary across records and are not class priors."""
    values = [
        probability
        for _, probabilities, _, _, _, _ in scored()
        for probability in probabilities
    ]
    winners = [
        max(range(10), key=lambda digit: (row[1][digit], -digit)) for row in scored()
    ]
    assert max(values) - min(values) > 0.25
    assert len(set(winners)) == 10
    assert len({round(value, 6) for value in values}) >= 80


def test_evaluation_row_order_is_key_invariant():
    """Reordered evaluation rows keep the same keyed probability distributions."""
    original = {row[0]: row[1] for row in scored()}
    bundle = tempfile.mkdtemp(prefix="pendigit-bundle-")
    shutil.copytree("/app/data", bundle, dirs_exist_ok=True)
    os.chmod(bundle, 0o755)
    eval_path = os.path.join(bundle, "evaluation_digits.csv")
    rows = read_rows(eval_path)
    with open(eval_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(reversed(rows))
    permuted = {row[0]: row[1] for row in load_scored(bundle)}
    assert original.keys() == permuted.keys()
    assert (
        max(
            abs(original[key][digit] - permuted[key][digit])
            for key in original
            for digit in range(10)
        )
        < 1e-10
    )
