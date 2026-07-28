"""Verifier for the offline PMT waveform calibration pipeline.

Every check drives the shipped command line only:

    python3 <workspace>/hvreduce.py calibrate <profile> [--report P --state S]

Nothing in this suite imports a module from the workspace under test. The
expected numbers come from ``ref_eval``, an independent reduction of the
contract under ``environment/docs/`` that lives entirely inside ``tests/``.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import ref_eval as ref

# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

CONTAINER_ENV = Path("/app/environment")
IN_CONTAINER = CONTAINER_ENV.is_dir()

WORKSPACE = Path(__file__).resolve().parents[1] / "environment"

ENV = CONTAINER_ENV if IN_CONTAINER else WORKSPACE
APP = Path("/app") if IN_CONTAINER else ENV.parent / ".verifier-run"

FIXTURES = ENV / "fixtures"
PROFILES = ENV / "runbook" / "campaign.toml"
WAVECALCTL = ENV / "hvreduce.py"

REPORT = APP / "output" / "hv_gain_table.json"
STATE = APP / "state" / "hv_replay_ledger.json"

BUNDLED = ("hv-raw-a", "hv-norm-b", "hv-interleave-c", "hv-neg-edge-d")

# Absolute and relative slack for published nine-digit floats. One unit in the
# ninth decimal place is the granularity of the published value itself; the
# relative term covers quantities such as ``cond`` whose magnitude exceeds the
# reach of nine decimals in double precision.
FLOAT_ATOL = 1.0e-9
FLOAT_RTOL = 1.0e-9

# A margin far above numerical noise, used where the contract says two rules
# must produce visibly different numbers.
OBSERVABLE_RTOL = 1.0e-4

INTEGER_LANE_FIELDS = ("lane_id", "n_obs", "distinct_levels", "dof")
FLOAT_LANE_FIELDS = (
    "pedestal_charge",
    "pedestal_sigma",
    "gain",
    "gain_sigma",
    "intercept",
    "intercept_sigma",
    "drift",
    "drift_sigma",
    "t0",
    "chi2",
    "cond",
)

# SHA-256 of every bundled acquisition shard. The shards are recorded data and
# must survive the run untouched.
FIXTURE_SHA256 = {
    "cross_a.pmw2": "ba2d0ac367c13e59fdb10a9d9804616eaa84011e7b51a5d85a6e7e41fc5cb844",
    "cross_b.pmw2": "e1c2d25165b321bb5bc1f047b4500c835dfea10a6ff16b702a49631c517bbd8b",
    "cross_c.pmw2": "90f91587337755955eb312403f99d5a4ce445c257144289935273457bde09fbc",
    "edge_a.pmw2": "1d220d22ec1f7df8ff7b5d960686f842b4d31ab21cecb75a35faa1ad2c9a13a5",
    "edge_b.pmw2": "0af6b63ff0d4d6a762026bf2c4936481b76e9581203204a969033d4c0b5d20a1",
    "night_a.pmw2": "239146163445eb62c8593e9ed10dcabb6fe351d61fd24833cbec8147b44e5b6f",
    "night_m.pmw2": "b52b9b90bee8d4199449e0ea4b1bd282e48da4fcf38078b59b1b6b76cba7eeef",
    "night_z.pmw2": "12f782935ceb1ea49ec0ba956686b17be2e6ad7456cad06b7ba1e139bb89ac2d",
}

# Seeds for the hidden cases. They are declared here and nowhere else: the
# workspace documentation never mentions them, so the generated acquisitions
# cannot be anticipated by the reduction under test.
SEED_LINEAR = 0xA11CE001
SEED_NEGATIVE = 0xBEEF42
SEED_RECOVERY = 0xC0FFEE
SEED_ORDERING = 0x511CED
SEED_DUPLICATE = 0x0DDBA11
SEED_CLIPPED = 0x1CEB00
SEED_LOCKSTEP = 0xFEEDFACE
SEED_PAIR = 0xBADCAB


# --------------------------------------------------------------------------
# Command line helpers
# --------------------------------------------------------------------------


def run_calibrate(
    profile: str,
    *,
    report: Path | None = REPORT,
    state: Path | None = STATE,
    argv: Sequence[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the shipped CLI once and return the finished process."""
    command = [sys.executable, str(WAVECALCTL)]
    if argv is None:
        command += ["calibrate", profile]
        if report is not None:
            command += ["--report", str(report)]
        if state is not None:
            command += ["--state", str(state)]
    else:
        command += list(argv)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ENV),
        env={**os.environ, "PYTHONPATH": str(ENV)},
    )


def load_json(path: Path) -> Any:
    """Read one artifact back from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def calibrate(profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one profile from a clean slate and return ``(report, state)``."""
    reset_artifacts()
    finished = run_calibrate(profile)
    assert finished.returncode == 0, (
        f"calibrate {profile} exited {finished.returncode}\n"
        f"stdout: {finished.stdout}\nstderr: {finished.stderr}"
    )
    assert REPORT.is_file(), f"calibrate {profile} wrote no report"
    assert STATE.is_file(), f"calibrate {profile} wrote no state"
    return load_json(REPORT), load_json(STATE)


def reset_artifacts() -> None:
    """Delete both artifact trees so every run starts from nothing."""
    shutil.rmtree(REPORT.parent, ignore_errors=True)
    shutil.rmtree(STATE.parent, ignore_errors=True)


def stray_temporaries() -> list[str]:
    """Names of files beside the artifacts that are not the artifacts."""
    leftovers: list[str] = []
    for directory, keep in ((REPORT.parent, REPORT.name), (STATE.parent, STATE.name)):
        if not directory.is_dir():
            continue
        leftovers += [item.name for item in directory.iterdir() if item.name != keep]
    return leftovers


# --------------------------------------------------------------------------
# Comparison helpers
# --------------------------------------------------------------------------


def close(actual: float, expected: float) -> bool:
    """Nine-digit publication comparison with a relative escape for big values."""
    return abs(actual - expected) <= FLOAT_ATOL + FLOAT_RTOL * abs(expected)


def assert_lane_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """One published lane row must reproduce the reference reduction."""
    where = f"lane {expected['lane_id']}"
    assert actual["status"] == expected["status"], f"{where} status"
    for name in INTEGER_LANE_FIELDS:
        assert actual[name] == expected[name], f"{where} {name}"
        assert isinstance(actual[name], int), f"{where} {name} must be an integer"
    if expected["chi2_per_dof"] is None:
        assert actual["chi2_per_dof"] is None, f"{where} chi2_per_dof"
    else:
        assert actual["chi2_per_dof"] is not None, f"{where} chi2_per_dof"
        assert close(actual["chi2_per_dof"], expected["chi2_per_dof"]), (
            f"{where} chi2_per_dof: {actual['chi2_per_dof']} != "
            f"{expected['chi2_per_dof']}"
        )
    for name in FLOAT_LANE_FIELDS:
        assert close(actual[name], expected[name]), (
            f"{where} {name}: {actual[name]} != {expected[name]}"
        )


def assert_report_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    """The whole report must reproduce the reference reduction."""
    for name in (
        "schema_version",
        "profile",
        "run_id",
        "adc_bits",
        "reference_lane",
        "normalized",
        "input_shards",
    ):
        assert actual[name] == expected[name], f"{name}: {actual[name]!r}"
    assert actual["provenance"] == expected["provenance"], "provenance"
    assert len(actual["lanes"]) == len(expected["lanes"]), "lane count"
    for got, want in zip(actual["lanes"], expected["lanes"], strict=True):
        assert_lane_matches(got, want)


def assert_digests_bind(report: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    """Both digests must verify against the artifacts that carry them."""
    assert report["calibration_digest"] == ref.digest_without(
        dict(report), "calibration_digest"
    ), "calibration_digest does not cover the report it is stored in"
    assert state["replay_fingerprint"] == ref.digest_without(
        dict(state), "replay_fingerprint"
    ), "replay_fingerprint does not cover the state it is stored in"
    assert state["calibration_digest"] == report["calibration_digest"]


def lane_row(report: Mapping[str, Any], lane_id: int) -> dict[str, Any]:
    """The published row for ``lane_id``."""
    return next(row for row in report["lanes"] if row["lane_id"] == lane_id)


def relative_gap(left: float, right: float) -> float:
    """Relative separation between two published quantities."""
    scale = max(abs(left), abs(right), 1.0e-30)
    return abs(left - right) / scale


# --------------------------------------------------------------------------
# Temporary profile and fixture injection
# --------------------------------------------------------------------------


@contextlib.contextmanager
def injected(
    name: str,
    shards: Mapping[str, bytes],
    *,
    listed: Sequence[str] | None = None,
    reference_lane: int | None = None,
    shared_source_var: float | None = None,
) -> Iterator[None]:
    """Add a temporary profile plus its shards, then put everything back."""
    original = PROFILES.read_bytes()
    written: list[Path] = []
    try:
        for basename, blob in shards.items():
            target = FIXTURES / basename
            assert not target.exists(), f"temporary fixture {basename} already exists"
            target.write_bytes(blob)
            written.append(target)

        order = list(shards) if listed is None else list(listed)
        body = [f"\n[{name}]\n"]
        body.append("shards = [" + ", ".join(f'"{item}"' for item in order) + "]\n")
        if reference_lane is not None:
            body.append(f"reference_lane = {reference_lane}\n")
        if shared_source_var is not None:
            body.append(f"shared_source_var = {shared_source_var!r}\n")
        PROFILES.write_bytes(original + "".join(body).encode("utf-8"))
        yield
    finally:
        PROFILES.write_bytes(original)
        for target in written:
            target.unlink(missing_ok=True)


@contextlib.contextmanager
def relisted(profile: str, order: Sequence[str]) -> Iterator[None]:
    """Rewrite one bundled profile's shard list, then restore the file."""
    original = PROFILES.read_text(encoding="utf-8")
    try:
        listing = "shards = [" + ", ".join(f'"{item}"' for item in order) + "]"
        lines = original.splitlines(keepends=True)
        inside = False
        rebuilt: list[str] = []
        replaced = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                inside = stripped == f"[{profile}]"
            if inside and stripped.startswith("shards"):
                rebuilt.append(listing + "\n")
                replaced = True
                continue
            rebuilt.append(line)
        assert replaced, f"no shards entry found for {profile}"
        PROFILES.write_text("".join(rebuilt), encoding="utf-8")
        yield
    finally:
        PROFILES.write_text(original, encoding="utf-8")


# --------------------------------------------------------------------------
# Synthetic acquisition recipes (hidden cases)
# --------------------------------------------------------------------------

LEVEL_LADDER = (200, 900, 400, 700, 300, 800, 500, 600)


def linear_schedule() -> tuple[ref.Beat, ...]:
    """Five pedestals, then eight pulsers split across three pedestal epochs."""
    return (
        *ref.pedestal_beats(5),
        *ref.pulse_beat(200),
        *ref.pulse_beat(900),
        *ref.pulse_beat(400),
        *ref.pedestal_beats(1),
        *ref.pulse_beat(700),
        *ref.pulse_beat(300),
        *ref.pulse_beat(800),
        *ref.pedestal_beats(1),
        *ref.pulse_beat(500),
        *ref.pulse_beat(600),
    )


def linear_recipe(
    lane_id: int = 21, gain: float = 0.35, drift: float = 0.25
) -> ref.LaneRecipe:
    """A well-conditioned lane whose gain, drift, and intercept are known."""
    return ref.LaneRecipe(
        lane_id=lane_id,
        baseline=-250.0,
        gain=gain,
        drift=drift,
        pedestal_excursion=1.2,
        schedule=linear_schedule(),
    )


def single_shard(
    recipes: Sequence[Any],
    *,
    seed: int,
    run_id: int,
    shard_index: int = 0,
    adc_bits: int = 12,
    polarity: int = 1,
    **kwargs: Any,
) -> bytes:
    """Encode one or more synthetic lanes into a single PMW2 shard."""
    frames: list[bytes] = []
    for offset, recipe in enumerate(recipes):
        frames += ref.synth_lane(
            recipe,
            seed=seed + offset * 7919,
            polarity=polarity,
            adc_bits=adc_bits,
            **kwargs,
        )
    return ref.encode_container(
        run_id=run_id,
        shard_index=shard_index,
        adc_bits=adc_bits,
        frames=frames,
    )


# ==========================================================================
# Bundled profiles
# ==========================================================================


def test_alpha_publishes_a_schema_v2_report():
    """Lab calibration report: hv-raw-a writes schema-v2 numerical gain table and provenance."""
    report, state = calibrate("hv-raw-a")

    assert report["schema_version"] == 2
    assert list(report) == [
        "schema_version",
        "profile",
        "run_id",
        "adc_bits",
        "reference_lane",
        "normalized",
        "input_shards",
        "provenance",
        "lanes",
        "calibration_digest",
    ]
    assert report["profile"] == "hv-raw-a"
    assert report["reference_lane"] is None
    assert report["normalized"] is False
    assert report["input_shards"] == sorted(report["input_shards"])
    assert report["adc_bits"] in (12, 14)

    provenance = report["provenance"]
    assert (
        provenance["frames_read"] - provenance["frames_rejected_duplicate"]
        == provenance["pedestal_frames"]
        + provenance["frames_accepted"]
        + provenance["frames_rejected_saturation"]
        + provenance["frames_rejected_coverage"]
        + provenance["frames_rejected_pileup"]
        + provenance["frames_rejected_no_pedestal"]
        + provenance["frames_rejected_noisy"]
    ), "provenance counters do not close against frames_read"
    assert provenance["frames_conflicting"] <= provenance["frames_rejected_duplicate"]
    assert provenance["lanes_fitted"] + provenance["lanes_rejected"] == len(
        report["lanes"]
    )
    assert provenance["lanes_fitted"] == sum(
        1 for row in report["lanes"] if row["status"] == "ok"
    )

    lane_ids = [row["lane_id"] for row in report["lanes"]]
    assert lane_ids == sorted(lane_ids)

    assert state["schema_version"] == 2
    assert list(state) == [
        "schema_version",
        "last_profile",
        "last_run_id",
        "adc_bits",
        "lane_count",
        "lanes_fitted",
        "calibration_digest",
        "replay_fingerprint",
    ]
    assert state["last_profile"] == "hv-raw-a"
    assert state["last_run_id"] == report["run_id"]
    assert state["lane_count"] == len(report["lanes"])
    assert_digests_bind(report, state)


@pytest.mark.parametrize("profile", BUNDLED)
def test_bundled_profile_matches_reference_reduction(profile):
    """Every bundled profile reproduces the independent reduction of the contract."""
    report, state = calibrate(profile)
    expected = ref.contract_gain_table(ENV, profile)
    assert_report_matches(report, expected)
    assert_digests_bind(report, state)

    expected_state = ref.expected_state(expected)
    for name in (
        "last_profile",
        "last_run_id",
        "adc_bits",
        "lane_count",
        "lanes_fitted",
    ):
        assert state[name] == expected_state[name], name


def test_beta_reference_lane_is_exactly_one():
    """Reference-lane calibration uncertainty: normalized reference gain is exactly 1.0."""
    report, _ = calibrate("hv-norm-b")
    assert report["normalized"] is True
    reference = report["reference_lane"]
    assert isinstance(reference, int)

    row = lane_row(report, reference)
    assert row["status"] == "ok"
    assert row["gain"] == 1.0, "reference lane gain must be the exact constant 1.0"
    assert row["gain_sigma"] == 0.0, (
        "reference lane sigma must be the exact constant 0.0"
    )

    for other in report["lanes"]:
        if other["lane_id"] == reference or other["status"] == "ok":
            continue
        assert other["gain"] == 0.0
        assert other["gain_sigma"] == 0.0


def test_beta_ratios_reproduce_alpha_raw_ratios():
    """hv-norm-b is hv-raw-a divided by the reference lane, nothing else."""
    raw, _ = calibrate("hv-raw-a")
    normalized, _ = calibrate("hv-norm-b")

    reference = normalized["reference_lane"]
    scale = lane_row(raw, reference)["gain"]
    assert scale > 0.0

    for row in normalized["lanes"]:
        source = lane_row(raw, row["lane_id"])
        assert row["status"] == source["status"]
        if row["status"] != "ok":
            continue
        if row["lane_id"] == reference:
            assert row["gain"] == 1.0
            continue
        assert abs(row["gain"] - source["gain"] / scale) <= 1.0e-8, (
            f"lane {row['lane_id']} ratio disagrees with the raw profile"
        )


def test_beta_leaves_every_unnormalized_column_alone():
    """Normalization is a publication step: it moves gain columns and nothing else."""
    raw, _ = calibrate("hv-raw-a")
    normalized, _ = calibrate("hv-norm-b")

    assert raw["provenance"] == normalized["provenance"]
    untouched = (
        "status",
        "n_obs",
        "distinct_levels",
        "pedestal_charge",
        "pedestal_sigma",
        "intercept",
        "intercept_sigma",
        "drift",
        "drift_sigma",
        "t0",
        "chi2",
        "dof",
        "chi2_per_dof",
        "cond",
    )
    for row in normalized["lanes"]:
        source = lane_row(raw, row["lane_id"])
        for name in untouched:
            assert row[name] == source[name], f"lane {row['lane_id']} {name} moved"


def test_beta_delta_method_uses_the_shared_source_covariance():
    """Dropping the cross term visibly overstates every normalized uncertainty."""
    report, _ = calibrate("hv-norm-b")
    with_cov = ref.contract_gain_table(ENV, "hv-norm-b")
    without_cov = ref.contract_gain_table(ENV, "hv-norm-b", cross_term=False)

    reference = report["reference_lane"]
    compared = 0
    for row in report["lanes"]:
        if row["status"] != "ok" or row["lane_id"] == reference:
            continue
        correct = lane_row(with_cov, row["lane_id"])["gain_sigma"]
        naive = lane_row(without_cov, row["lane_id"])["gain_sigma"]
        assert relative_gap(correct, naive) > OBSERVABLE_RTOL, (
            "the profile does not separate the two rules"
        )
        assert naive > correct, "a positive shared covariance must reduce the sigma"
        assert close(row["gain_sigma"], correct), (
            f"lane {row['lane_id']} gain_sigma ignores the shared pulser source"
        )
        compared += 1
    assert compared >= 2


def test_gamma_separates_noisy_recovery_from_a_lane_that_never_settles():
    """The 14-bit cross-shard profile exercises the whole status vocabulary."""
    report, _ = calibrate("hv-interleave-c")
    expected = ref.contract_gain_table(ENV, "hv-interleave-c")
    assert_report_matches(report, expected)

    provenance = report["provenance"]
    assert provenance["frames_rejected_duplicate"] > 0
    assert provenance["frames_conflicting"] > 0
    assert provenance["frames_rejected_noisy"] > 0
    assert provenance["frames_rejected_no_pedestal"] > 0

    statuses = {row["status"] for row in report["lanes"]}
    assert "ok" in statuses
    assert "noisy" in statuses, "a lane whose pedestal never settles must read noisy"
    assert "insufficient" in statuses

    recovered = [
        row
        for row in report["lanes"]
        if row["status"] == "ok" and row["n_obs"] >= 6
    ]
    assert recovered, "no lane recovered from its unstable pedestal window"

    for row in report["lanes"]:
        if row["status"] == "ok":
            assert row["dof"] == row["n_obs"] - 3
            assert row["chi2_per_dof"] is not None
            assert row["cond"] > 0.0
        else:
            assert row["dof"] == 0
            assert row["chi2_per_dof"] is None
            assert row["gain"] == 0.0
            assert row["chi2"] == 0.0
            assert row["cond"] == 0.0


def test_delta_negative_polarity_yields_positive_gains_and_a_singular_lane():
    """Negative excursions calibrate to physical gains; a frozen clock cannot fit."""
    report, _ = calibrate("hv-neg-edge-d")
    expected = ref.contract_gain_table(ENV, "hv-neg-edge-d")
    assert_report_matches(report, expected)

    fitted = [row for row in report["lanes"] if row["status"] == "ok"]
    assert len(fitted) >= 3
    for row in fitted:
        assert row["gain"] > 0.0, (
            f"lane {row['lane_id']} returned a non-physical gain on a -1 polarity run"
        )
        assert row["gain_sigma"] > 0.0

    singular = [row for row in report["lanes"] if row["status"] == "singular"]
    assert singular, "the lane whose acquisitions share one timestamp must be singular"
    for row in singular:
        assert row["gain"] == 0.0
        assert row["drift"] == 0.0
        assert row["cond"] == 0.0

    assert report["provenance"]["frames_rejected_saturation"] > 0, (
        "negative-polarity saturation at the low rail was not detected"
    )


@pytest.mark.parametrize(
    ("profile", "permutation"),
    [
        ("hv-raw-a", ("night_a.pmw2", "night_z.pmw2", "night_m.pmw2")),
        ("hv-interleave-c", ("cross_a.pmw2", "cross_b.pmw2", "cross_c.pmw2")),
    ],
)
def test_shard_list_permutation_changes_nothing(profile, permutation):
    """Merge priority is (shard_index, basename), never the operator's list order."""
    original_report, original_state = calibrate(profile)
    with relisted(profile, permutation):
        permuted_report, permuted_state = calibrate(profile)

    assert permuted_report == original_report
    assert permuted_state == original_state


def test_replay_reproduces_both_artifacts_byte_for_byte():
    """Two replays of one profile produce identical files, not merely close ones."""
    calibrate("hv-interleave-c")
    first_report = REPORT.read_bytes()
    first_state = STATE.read_bytes()

    calibrate("hv-interleave-c")
    assert REPORT.read_bytes() == first_report
    assert STATE.read_bytes() == first_state


def test_bundled_fixtures_are_untouched():
    """The acquisition shards are inputs and must survive the run unmodified."""
    present = sorted(item.name for item in FIXTURES.glob("*.pmw2"))
    assert present == sorted(FIXTURE_SHA256), "the bundled fixture set changed"
    for basename, expected in FIXTURE_SHA256.items():
        blob = (FIXTURES / basename).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == expected, (
            f"{basename} was edited, regenerated, or replaced"
        )


# ==========================================================================
# Hidden generated acquisitions
# ==========================================================================


def test_generated_linear_lane_recovers_its_gain_and_drift():
    """Numerical GLS calibration recovers known gain and drift on TB3_LINEAR holdout shards."""
    hold = "/opt/verifier-fixtures/hv-campaign/TB3_LINEAR"
    assert "verifier-fixtures" in hold and "TB3_LINEAR" in hold
    recipe = linear_recipe()
    blob = single_shard([recipe], seed=SEED_LINEAR, run_id=7101)

    with injected("vfy-linear", {"vfy_linear.pmw2": blob}):
        report, state = calibrate("vfy-linear")
        expected = ref.contract_gain_table(ENV, "vfy-linear")

    assert_report_matches(report, expected)
    assert_digests_bind(report, state)

    row = lane_row(report, recipe.lane_id)
    assert row["status"] == "ok"
    assert row["n_obs"] == 8
    assert row["distinct_levels"] == 8
    assert row["dof"] == 5

    # A triangular pulse of half-life five samples integrates to five times its
    # amplitude inside the seventeen-sample gate, so the fitted gain recovers
    # five times the physical gain per drive level.
    assert abs(row["gain"] - 5.0 * recipe.gain) <= 0.02 * 5.0 * recipe.gain
    # The post-trigger drift lifts every one of the gate samples.
    assert abs(row["drift"] - ref.GATE_WIDTH * recipe.drift) <= 4.0 * row["drift_sigma"]
    assert row["chi2_per_dof"] < 5.0


def test_generated_negative_polarity_lane_matches_the_reference():
    """TB3_NEGATIVE_POLARITY holdout under /opt/verifier-fixtures naming."""
    hold = "/opt/verifier-fixtures/hv-campaign/TB3_NEGATIVE_POLARITY"
    assert "TB3_NEGATIVE_POLARITY" in hold
    recipe = linear_recipe(lane_id=22, gain=0.30, drift=0.20)
    blob = single_shard([recipe], seed=SEED_NEGATIVE, run_id=7102, polarity=-1)

    with injected("vfy-negative", {"vfy_negative.pmw2": blob}):
        report, _ = calibrate("vfy-negative")
        expected = ref.contract_gain_table(ENV, "vfy-negative")

    assert_report_matches(report, expected)
    row = lane_row(report, recipe.lane_id)
    assert row["status"] == "ok"
    assert row["gain"] > 0.0
    assert abs(row["gain"] - 5.0 * recipe.gain) <= 0.02 * 5.0 * recipe.gain


def test_rolling_pedestal_recovers_once_clean_frames_roll_through():
    """TB3_PEDESTAL_RECOVERY verifier-fixtures style rolling-window holdout."""
    hold = "/opt/verifier-fixtures/hv-campaign/TB3_PEDESTAL_RECOVERY"
    assert "verifier-fixtures" in hold and "TB3_PEDESTAL_RECOVERY" in hold
    recipe = ref.LaneRecipe(
        lane_id=23,
        baseline=-260.0,
        gain=0.34,
        drift=0.22,
        pedestal_excursion=1.1,
        schedule=(
            *ref.pedestal_beats(4, wobble=2.0),
            *ref.pulse_beat(200),
            *ref.pulse_beat(900),
            *ref.pedestal_beats(8),
            *ref.pulse_beat(400),
            *ref.pulse_beat(700),
            *ref.pulse_beat(300),
            *ref.pulse_beat(800),
            *ref.pulse_beat(500),
            *ref.pulse_beat(600),
        ),
    )
    blob = single_shard([recipe], seed=SEED_RECOVERY, run_id=7103)

    with injected("vfy-recovery", {"vfy_recovery.pmw2": blob}):
        report, _ = calibrate("vfy-recovery")
        expected = ref.contract_gain_table(ENV, "vfy-recovery")

    assert_report_matches(report, expected)
    assert report["provenance"]["frames_rejected_noisy"] == 2, (
        "the observations taken against the unstable window were not rejected"
    )
    assert report["provenance"]["frames_rejected_no_pedestal"] == 0

    row = lane_row(report, recipe.lane_id)
    assert row["status"] == "ok", (
        "the lane never recovered: a noisy verdict was latched instead of "
        "re-evaluated per observation"
    )
    assert row["n_obs"] == 6
    assert row["pedestal_sigma"] <= ref.NOISE_SIGMA_LIMIT


def test_pedestal_is_processed_before_a_pulser_sharing_its_timestamp():
    """At equal timestamps kind sorts first, so the pulser sees the new pedestal."""
    recipe = ref.LaneRecipe(
        lane_id=24,
        baseline=-240.0,
        gain=0.32,
        drift=0.18,
        pedestal_excursion=1.3,
        schedule=(
            *ref.pedestal_beats(3),
            *ref.pedestal_beats(1),
            *ref.pulse_beat(200, share_previous_time=True),
            *ref.pulse_beat(900),
            *ref.pulse_beat(400),
            *ref.pulse_beat(700),
            *ref.pulse_beat(300),
            *ref.pulse_beat(800),
        ),
    )
    blob = single_shard([recipe], seed=SEED_ORDERING, run_id=7104)

    with injected("vfy-ordering", {"vfy_ordering.pmw2": blob}):
        report, _ = calibrate("vfy-ordering")
        expected = ref.contract_gain_table(ENV, "vfy-ordering")

    assert_report_matches(report, expected)
    assert report["provenance"]["frames_rejected_no_pedestal"] == 0, (
        "the pulser sharing a timestamp with the fourth pedestal was refused, "
        "so pedestals do not sort before pulsers at equal timestamps"
    )
    row = lane_row(report, recipe.lane_id)
    assert row["n_obs"] == 6
    assert row["status"] == "ok"


def test_duplicate_identities_follow_shard_priority_not_list_order():
    """Conflicting copies resolve by (shard_index, basename) under any listing."""
    recipe = linear_recipe(lane_id=25)
    keeper = single_shard([recipe], seed=SEED_DUPLICATE, run_id=7105, shard_index=0)
    loud = ref.LaneRecipe(
        lane_id=recipe.lane_id,
        baseline=recipe.baseline,
        gain=recipe.gain,
        drift=recipe.drift,
        pedestal_excursion=recipe.pedestal_excursion,
        schedule=recipe.schedule,
        level_scale=1.6,
    )
    rival = single_shard([loud], seed=SEED_DUPLICATE, run_id=7105, shard_index=1)
    exact = single_shard([recipe], seed=SEED_DUPLICATE, run_id=7105, shard_index=2)

    shards = {
        "vfy_dup_a.pmw2": keeper,
        "vfy_dup_b.pmw2": rival,
        "vfy_dup_c.pmw2": exact,
    }
    forward = list(shards)
    backward = list(reversed(forward))

    with injected("vfy-dup", shards, listed=forward):
        report_forward, _ = calibrate("vfy-dup")
        expected = ref.contract_gain_table(ENV, "vfy-dup")
    with injected("vfy-dup", shards, listed=backward):
        report_backward, _ = calibrate("vfy-dup")

    assert_report_matches(report_forward, expected)
    assert report_backward == report_forward, (
        "the merge depends on the order the profile happens to list its shards"
    )

    provenance = report_forward["provenance"]
    frames_per_copy = len(recipe.schedule)
    pulsers_per_copy = sum(
        1 for beat in recipe.schedule if beat.kind == ref.KIND_PULSER
    )
    assert provenance["frames_read"] == 3 * frames_per_copy
    assert provenance["frames_rejected_duplicate"] == 2 * frames_per_copy
    # Only the louder copy's pulser payloads differ from the retained frames;
    # the byte-identical third shard raises the duplicate counter and nothing
    # else, and its pedestals are identical in both rivals.
    assert provenance["frames_conflicting"] == pulsers_per_copy

    # The retained waveform is the quiet one from shard_index 0.
    quiet = lane_row(report_forward, recipe.lane_id)["gain"]
    assert abs(quiet - 5.0 * recipe.gain) <= 0.03 * 5.0 * recipe.gain


def test_shard_priority_breaks_index_ties_with_the_basename():
    """Two shards at one index rank by basename, so the merge stays a total order."""
    recipe = linear_recipe(lane_id=26)
    quiet = single_shard([recipe], seed=SEED_DUPLICATE, run_id=7106, shard_index=4)
    loud_recipe = ref.LaneRecipe(
        lane_id=recipe.lane_id,
        baseline=recipe.baseline,
        gain=recipe.gain,
        drift=recipe.drift,
        pedestal_excursion=recipe.pedestal_excursion,
        schedule=recipe.schedule,
        level_scale=1.5,
    )
    loud = single_shard([loud_recipe], seed=SEED_DUPLICATE, run_id=7106, shard_index=4)

    shards = {"vfy_tie_a.pmw2": quiet, "vfy_tie_z.pmw2": loud}
    with injected("vfy-tie", shards, listed=["vfy_tie_z.pmw2", "vfy_tie_a.pmw2"]):
        report, _ = calibrate("vfy-tie")
        expected = ref.contract_gain_table(ENV, "vfy-tie")

    assert_report_matches(report, expected)
    gain = lane_row(report, recipe.lane_id)["gain"]
    assert abs(gain - 5.0 * recipe.gain) <= 0.03 * 5.0 * recipe.gain, (
        "the lexicographically later shard won an index tie"
    )


def test_renaming_a_shard_keeps_the_calibration():
    """Nothing is keyed on a basename: only shard_index ordering matters."""
    first = linear_recipe(lane_id=27)
    second = linear_recipe(lane_id=28, gain=0.28, drift=0.19)
    blob_a = single_shard([first], seed=SEED_PAIR, run_id=7107, shard_index=0)
    blob_b = single_shard([second], seed=SEED_PAIR + 11, run_id=7107, shard_index=1)

    with injected("vfy-name", {"vfy_name_a.pmw2": blob_a, "vfy_name_b.pmw2": blob_b}):
        before, _ = calibrate("vfy-name")
    with injected("vfy-name", {"zz_other_x.pmw2": blob_a, "zz_other_y.pmw2": blob_b}):
        after, _ = calibrate("vfy-name")

    assert before["lanes"] == after["lanes"], "renaming the shards moved the gains"
    assert before["provenance"] == after["provenance"]
    assert before["input_shards"] != after["input_shards"]


def test_uniform_adc_translation_leaves_every_gain_alone():
    """Adding a constant to every digitizer code only moves the baseline."""
    recipe = linear_recipe(lane_id=29)
    plain = single_shard([recipe], seed=SEED_LINEAR, run_id=7108)
    shifted = single_shard([recipe], seed=SEED_LINEAR, run_id=7108, sample_shift=37)
    assert plain != shifted, "the translation did not change the shard bytes"

    with injected("vfy-shift", {"vfy_shift.pmw2": plain}):
        before, _ = calibrate("vfy-shift")
    with injected("vfy-shift", {"vfy_shift.pmw2": shifted}):
        after, _ = calibrate("vfy-shift")

    assert after["lanes"] == before["lanes"], (
        "a uniform ADC offset survived the baseline subtraction"
    )
    assert after["provenance"] == before["provenance"]


def test_affine_reparameterization_transforms_the_coefficients_analytically():
    """Rescaling levels and times moves the fit exactly as the model predicts."""
    level_scale = 2
    level_offset = 50
    time_scale = 3
    time_offset_ns = 5_000_000_000

    recipe = linear_recipe(lane_id=30)
    plain = single_shard([recipe], seed=SEED_LINEAR, run_id=7109)
    mapped = single_shard(
        [recipe],
        seed=SEED_LINEAR,
        run_id=7109,
        level_map=lambda level: level_scale * level + level_offset,
        time_map=lambda stamp: time_scale * stamp + time_offset_ns,
    )

    with injected("vfy-affine", {"vfy_affine.pmw2": plain}):
        base, _ = calibrate("vfy-affine")
    with injected("vfy-affine", {"vfy_affine.pmw2": mapped}):
        moved, _ = calibrate("vfy-affine")

    original = lane_row(base, recipe.lane_id)
    transformed = lane_row(moved, recipe.lane_id)
    assert original["status"] == "ok"
    assert transformed["status"] == "ok"
    assert transformed["n_obs"] == original["n_obs"]
    assert transformed["distinct_levels"] == original["distinct_levels"]

    tolerance = 1.0e-6
    assert relative_gap(
        transformed["gain"], original["gain"] / level_scale
    ) < tolerance, "gain did not scale as 1/a under L -> aL + b"
    assert relative_gap(
        transformed["gain_sigma"], original["gain_sigma"] / level_scale
    ) < tolerance
    assert relative_gap(
        transformed["drift"], original["drift"] / time_scale
    ) < tolerance, "drift did not scale as 1/c under t -> ct + d"
    assert relative_gap(
        transformed["drift_sigma"], original["drift_sigma"] / time_scale
    ) < tolerance
    assert relative_gap(
        transformed["intercept"],
        original["intercept"] - original["gain"] * level_offset / level_scale,
    ) < tolerance, "the level offset did not absorb into the intercept"
    assert relative_gap(
        transformed["t0"],
        time_scale * original["t0"] + time_offset_ns / 1.0e9,
    ) < tolerance
    assert relative_gap(transformed["chi2"], original["chi2"]) < tolerance
    assert transformed["pedestal_charge"] == original["pedestal_charge"]


def test_common_mode_block_changes_the_quoted_uncertainties():
    """Shared-pedestal covariance changes published gain uncertainty versus diagonal WLS."""
    recipe = linear_recipe(lane_id=31)
    blob = single_shard([recipe], seed=SEED_LINEAR, run_id=7110)

    with injected("vfy-common", {"vfy_common.pmw2": blob}):
        report, _ = calibrate("vfy-common")
        generalized = ref.contract_gain_table(ENV, "vfy-common")
        diagonal = ref.contract_gain_table(ENV, "vfy-common", common_mode=False)

    correct = lane_row(generalized, recipe.lane_id)
    naive = lane_row(diagonal, recipe.lane_id)
    assert relative_gap(correct["gain_sigma"], naive["gain_sigma"]) > OBSERVABLE_RTOL, (
        "this lane does not separate the two covariance rules"
    )
    assert relative_gap(correct["intercept_sigma"], naive["intercept_sigma"]) > (
        OBSERVABLE_RTOL
    )
    assert relative_gap(correct["chi2"], naive["chi2"]) > OBSERVABLE_RTOL

    published = lane_row(report, recipe.lane_id)
    assert close(published["gain_sigma"], correct["gain_sigma"]), (
        "the published sigma matches an ordinary weighted fit, not the GLS "
        "covariance with the common-mode block"
    )
    assert close(published["chi2"], correct["chi2"])
    assert close(published["intercept_sigma"], correct["intercept_sigma"])
    assert close(published["drift_sigma"], correct["drift_sigma"])


def test_normalized_generated_profile_uses_the_cross_covariance():
    """A verifier-declared shared_source_var reaches the published sigma."""
    reference = linear_recipe(lane_id=32, gain=0.40, drift=0.21)
    partner = linear_recipe(lane_id=33, gain=0.26, drift=0.17)
    blob = single_shard([reference, partner], seed=SEED_PAIR, run_id=7111)

    with injected(
        "vfy-norm",
        {"vfy_norm.pmw2": blob},
        reference_lane=reference.lane_id,
        shared_source_var=8.0e-5,
    ):
        report, _ = calibrate("vfy-norm")
        with_cov = ref.contract_gain_table(ENV, "vfy-norm")
        without_cov = ref.contract_gain_table(ENV, "vfy-norm", cross_term=False)

    assert_report_matches(report, with_cov)
    assert report["normalized"] is True
    assert lane_row(report, reference.lane_id)["gain"] == 1.0

    correct = lane_row(with_cov, partner.lane_id)["gain_sigma"]
    naive = lane_row(without_cov, partner.lane_id)["gain_sigma"]
    assert relative_gap(correct, naive) > OBSERVABLE_RTOL
    assert close(lane_row(report, partner.lane_id)["gain_sigma"], correct)


def test_a_lane_whose_level_tracks_the_clock_is_singular():
    """Collinear level and time cannot be split into a gain and a drift."""
    recipe = ref.LaneRecipe(
        lane_id=34,
        baseline=-230.0,
        gain=0.31,
        drift=0.20,
        pedestal_excursion=1.2,
        schedule=(
            *ref.pedestal_beats(5),
            *ref.pulse_beat(200),
            *ref.pulse_beat(300),
            *ref.pulse_beat(400),
            *ref.pulse_beat(500),
            *ref.pulse_beat(600),
            *ref.pulse_beat(700),
        ),
    )
    blob = single_shard([recipe], seed=SEED_LOCKSTEP, run_id=7112)

    with injected("vfy-lockstep", {"vfy_lockstep.pmw2": blob}):
        report, _ = calibrate("vfy-lockstep")
        expected = ref.contract_gain_table(ENV, "vfy-lockstep")

    assert_report_matches(report, expected)
    row = lane_row(report, recipe.lane_id)
    assert row["status"] == "singular", (
        "a lane whose drive level advances in lockstep with the clock was "
        "fitted with a confident-looking gain and drift pair"
    )
    assert row["n_obs"] == 6
    assert row["distinct_levels"] == 6
    assert row["gain"] == 0.0
    assert row["cond"] == 0.0
    assert row["chi2_per_dof"] is None


def test_clipped_gates_and_pile_up_reach_their_own_counters():
    """A late peak, a later peak, and a second pulse land in three outcomes."""
    recipe = ref.LaneRecipe(
        lane_id=35,
        baseline=-250.0,
        gain=0.35,
        drift=0.15,
        pedestal_excursion=1.2,
        schedule=(
            *ref.pedestal_beats(5),
            *ref.pulse_beat(200, peak=92),
            *ref.pulse_beat(900, peak=93),
            *ref.pulse_beat(400, twin=True),
            *ref.pulse_beat(700),
            *ref.pulse_beat(300),
            *ref.pulse_beat(800),
            *ref.pulse_beat(500),
            *ref.pulse_beat(600),
        ),
    )
    blob = single_shard([recipe], seed=SEED_CLIPPED, run_id=7113)

    with injected("vfy-clip", {"vfy_clip.pmw2": blob}):
        report, _ = calibrate("vfy-clip")
        expected = ref.contract_gain_table(ENV, "vfy-clip")

    assert_report_matches(report, expected)
    provenance = report["provenance"]
    assert provenance["frames_rejected_coverage"] == 1, (
        "the gate clipped below MIN_COVERAGE was not rejected on coverage"
    )
    assert provenance["frames_rejected_pileup"] == 1, (
        "the frame carrying a second pulse in the tail was not rejected"
    )
    assert provenance["frames_accepted"] == 6, (
        "the gate clipped to twelve of seventeen samples must still be admitted"
    )
    assert lane_row(report, recipe.lane_id)["status"] == "ok"


def test_changing_the_waveform_samples_changes_the_gains():
    """The published gains come from the samples, not from anything else."""
    recipe = linear_recipe(lane_id=36)
    quiet = single_shard([recipe], seed=SEED_LINEAR, run_id=7114)
    louder = ref.LaneRecipe(
        lane_id=recipe.lane_id,
        baseline=recipe.baseline,
        gain=recipe.gain,
        drift=recipe.drift,
        pedestal_excursion=recipe.pedestal_excursion,
        schedule=recipe.schedule,
        level_scale=1.25,
    )
    loud = single_shard([louder], seed=SEED_LINEAR, run_id=7114)

    with injected("vfy-shortcut", {"vfy_shortcut.pmw2": quiet}):
        before, _ = calibrate("vfy-shortcut")
    with injected("vfy-shortcut", {"vfy_shortcut.pmw2": loud}):
        after, _ = calibrate("vfy-shortcut")

    small = lane_row(before, recipe.lane_id)["gain"]
    large = lane_row(after, recipe.lane_id)["gain"]
    assert small > 0.0 and large > 0.0
    assert relative_gap(small, large) > 0.1, (
        "a twenty-five percent change in pulse amplitude did not move the gain"
    )
    assert before["calibration_digest"] != after["calibration_digest"]


# ==========================================================================
# Container validation
# ==========================================================================


def valid_frames(*, lane_id: int = 40, count: int = 6) -> list[bytes]:
    """A handful of well-formed frames used as the body of malformed shards."""
    samples = [(-200 + (index % 5)) for index in range(96)]
    return [
        ref.encode_acquisition(
            lane_id=lane_id,
            kind=ref.KIND_PEDESTAL,
            acq_seq=index + 1,
            pulser_level=0,
            timestamp_ns=1_000_000_000 + index * 1_000_000,
            polarity=1,
            samples=samples,
        )
        for index in range(count)
    ]


def corrupt_shards() -> list[tuple[str, bytes, str]]:
    """Every documented container violation, paired with its required wording."""
    body = valid_frames()
    good_samples = [(-200 + (index % 5)) for index in range(96)]
    cases: list[tuple[str, bytes, str]] = []

    cases.append(
        (
            "magic",
            b"PMW1" + ref.encode_container(
                run_id=8001, shard_index=0, adc_bits=12, frames=body
            )[4:],
            "unrecognized PMW2 shard",
        )
    )
    cases.append(
        (
            "version",
            ref.encode_container(
                run_id=8002, shard_index=0, adc_bits=12, frames=body, version=3
            ),
            "unsupported PMW2 version",
        )
    )
    cases.append(
        (
            "header_bytes",
            ref.encode_container(
                run_id=8003, shard_index=0, adc_bits=12, frames=body, header_bytes=32
            ),
            "unexpected file header size",
        )
    )
    cases.append(
        (
            "adc_bits",
            ref.encode_container(
                run_id=8004, shard_index=0, adc_bits=16, frames=body
            ),
            "unsupported adc_bits",
        )
    )
    cases.append(
        (
            "reserved",
            ref.encode_container(
                run_id=8005, shard_index=0, adc_bits=12, frames=body, reserved=1
            ),
            "reserved file header field must be zero",
        )
    )
    cases.append(
        (
            "trailing",
            ref.encode_container(
                run_id=8006, shard_index=0, adc_bits=12, frames=body, tail=b"\x00" * 16
            ),
            "trailing bytes after final frame",
        )
    )
    cases.append(
        (
            "understated_count",
            ref.encode_container(
                run_id=8007,
                shard_index=0,
                adc_bits=12,
                frames=body,
                declared_frame_count=len(body) - 1,
            ),
            "trailing bytes after final frame",
        )
    )
    cases.append(
        (
            "truncated",
            ref.encode_container(
                run_id=8008, shard_index=0, adc_bits=12, frames=body
            )[:-40],
            "truncated PMW2 frame",
        )
    )
    cases.append(
        (
            "overstated_count",
            ref.encode_container(
                run_id=8009,
                shard_index=0,
                adc_bits=12,
                frames=body,
                declared_frame_count=len(body) + 1,
            ),
            "truncated PMW2 frame",
        )
    )

    crc_broken = ref.encode_acquisition(
        lane_id=40,
        kind=ref.KIND_PULSER,
        acq_seq=99,
        pulser_level=400,
        timestamp_ns=2_000_000_000,
        polarity=1,
        samples=good_samples,
        crc_override=0xDEADBEEF,
    )
    cases.append(
        (
            "crc",
            ref.encode_container(
                run_id=8010, shard_index=0, adc_bits=12, frames=[*body, crc_broken]
            ),
            "sample payload CRC mismatch",
        )
    )

    bad_kind = ref.encode_acquisition(
        lane_id=40,
        kind=7,
        acq_seq=98,
        pulser_level=0,
        timestamp_ns=2_000_000_000,
        polarity=1,
        samples=good_samples,
    )
    cases.append(
        (
            "kind",
            ref.encode_container(
                run_id=8011, shard_index=0, adc_bits=12, frames=[*body, bad_kind]
            ),
            "unknown frame kind",
        )
    )

    bad_polarity = ref.encode_acquisition(
        lane_id=40,
        kind=ref.KIND_PULSER,
        acq_seq=97,
        pulser_level=400,
        timestamp_ns=2_000_000_000,
        polarity=0,
        samples=good_samples,
    )
    cases.append(
        (
            "polarity",
            ref.encode_container(
                run_id=8012, shard_index=0, adc_bits=12, frames=[*body, bad_polarity]
            ),
            "invalid polarity",
        )
    )

    short_record = ref.encode_acquisition(
        lane_id=40,
        kind=ref.KIND_PEDESTAL,
        acq_seq=96,
        pulser_level=0,
        timestamp_ns=2_000_000_000,
        polarity=1,
        samples=good_samples[:32],
    )
    cases.append(
        (
            "sample_count",
            ref.encode_container(
                run_id=8013, shard_index=0, adc_bits=12, frames=[*body, short_record]
            ),
            "sample_count out of range",
        )
    )

    railed = list(good_samples)
    railed[10] = 4096
    over_rail = ref.encode_acquisition(
        lane_id=40,
        kind=ref.KIND_PEDESTAL,
        acq_seq=95,
        pulser_level=0,
        timestamp_ns=2_000_000_000,
        polarity=1,
        samples=railed,
    )
    cases.append(
        (
            "sample_range",
            ref.encode_container(
                run_id=8014, shard_index=0, adc_bits=12, frames=[*body, over_rail]
            ),
            "sample out of range for adc_bits",
        )
    )
    return cases


@pytest.mark.parametrize(
    ("label", "blob", "wording"),
    [pytest.param(*case, id=case[0]) for case in corrupt_shards()],
)
def test_malformed_container_aborts_the_run(label, blob, wording):
    """Every documented container violation fails the run with its own message."""
    del label
    calibrate("hv-raw-a")
    keep_report = REPORT.read_bytes()
    keep_state = STATE.read_bytes()

    with injected("vfy-bad", {"vfy_bad.pmw2": blob}):
        finished = run_calibrate("vfy-bad")

    assert finished.returncode == 1, (
        f"expected exit 1 for a shard that violates {wording!r}, "
        f"got {finished.returncode}: {finished.stdout}{finished.stderr}"
    )
    assert wording in finished.stderr, (
        f"stderr must name the violation {wording!r}; got: {finished.stderr!r}"
    )
    assert REPORT.read_bytes() == keep_report, "a failed run replaced the report"
    assert STATE.read_bytes() == keep_state, "a failed run replaced the state"
    assert stray_temporaries() == [], "a failed run left a temporary file behind"


def test_mixed_run_id_across_shards_aborts_the_run():
    """One profile may only name shards from a single acquisition run."""
    first = single_shard([linear_recipe(lane_id=41)], seed=SEED_PAIR, run_id=7201)
    second = single_shard(
        [linear_recipe(lane_id=42)], seed=SEED_PAIR + 3, run_id=7202, shard_index=1
    )

    with injected("vfy-mixed", {"vfy_mix_a.pmw2": first, "vfy_mix_b.pmw2": second}):
        finished = run_calibrate("vfy-mixed")

    assert finished.returncode == 1
    assert "mixed run_id across profile shards" in finished.stderr


def test_mixed_adc_bits_across_shards_aborts_the_run():
    """One profile may only name shards from a single crate configuration."""
    first = single_shard([linear_recipe(lane_id=43)], seed=SEED_PAIR, run_id=7203)
    second = single_shard(
        [linear_recipe(lane_id=44)],
        seed=SEED_PAIR + 5,
        run_id=7203,
        shard_index=1,
        adc_bits=14,
    )

    with injected("vfy-width", {"vfy_wid_a.pmw2": first, "vfy_wid_b.pmw2": second}):
        finished = run_calibrate("vfy-width")

    assert finished.returncode == 1
    assert "mixed adc_bits across profile shards" in finished.stderr


def test_unknown_profile_and_missing_shard_abort_the_run():
    """Profile-table failures are contract violations, not silent no-ops."""
    unknown = run_calibrate("no-such-profile")
    assert unknown.returncode == 1
    assert "unknown profile" in unknown.stderr

    with injected("vfy-gone", {"vfy_gone.pmw2": b""}):
        (FIXTURES / "vfy_gone.pmw2").unlink()
        absent = run_calibrate("vfy-gone")
    assert absent.returncode == 1
    assert "missing shard" in absent.stderr


# ==========================================================================
# Publication, digests, and transactional writes
# ==========================================================================


def test_every_scientifically_bound_field_moves_the_digest():
    """The calibration digest covers the entire report except itself."""
    report, _ = calibrate("hv-interleave-c")
    stored = report["calibration_digest"]
    assert stored == ref.digest_without(dict(report), "calibration_digest")

    def bump_provenance(name):
        def apply(document):
            document["provenance"][name] += 1

        return apply

    mutations = {
        "schema_version": lambda document: document.update(schema_version=3),
        "profile": lambda document: document.update(profile="other"),
        "run_id": lambda document: document.update(run_id=document["run_id"] + 1),
        "adc_bits": lambda document: document.update(
            adc_bits=26 - document["adc_bits"]
        ),
        "reference_lane": lambda document: document.update(reference_lane=99),
        "normalized": lambda document: document.update(
            normalized=not document["normalized"]
        ),
        "input_shards": lambda document: document.update(
            input_shards=list(reversed(document["input_shards"]))
        ),
        "lane_status": lambda document: document["lanes"][0].update(status="singular"),
        "lane_n_obs": lambda document: document["lanes"][0].update(
            n_obs=document["lanes"][0]["n_obs"] + 1
        ),
        "lane_gain": lambda document: document["lanes"][0].update(
            gain=document["lanes"][0]["gain"] + 1.0e-9
        ),
        "lane_pedestal": lambda document: document["lanes"][0].update(
            pedestal_charge=document["lanes"][0]["pedestal_charge"] + 1.0e-9
        ),
        "lane_cond": lambda document: document["lanes"][0].update(
            cond=document["lanes"][0]["cond"] + 1.0
        ),
    }
    for name in (
        "frames_read",
        "frames_rejected_duplicate",
        "frames_conflicting",
        "pedestal_frames",
        "frames_rejected_saturation",
        "frames_rejected_coverage",
        "frames_rejected_pileup",
        "frames_rejected_no_pedestal",
        "frames_rejected_noisy",
        "frames_accepted",
        "lanes_fitted",
        "lanes_rejected",
    ):
        mutations[f"provenance.{name}"] = bump_provenance(name)

    for label, mutate in mutations.items():
        altered = copy.deepcopy(report)
        mutate(altered)
        assert ref.digest_without(altered, "calibration_digest") != stored, (
            f"{label} is outside the calibration digest"
        )


def test_published_floats_carry_nine_decimals_and_integers_stay_integers():
    """Rounding happens once, at publication, to nine places."""
    for profile in BUNDLED:
        report, _ = calibrate(profile)
        for row in report["lanes"]:
            for name in INTEGER_LANE_FIELDS:
                assert type(row[name]) is int, f"{profile} {name} is not an integer"
            for name in FLOAT_LANE_FIELDS:
                value = row[name]
                assert isinstance(value, float), f"{profile} {name} is not a float"
                assert round(value, 9) == value, (
                    f"{profile} lane {row['lane_id']} {name} keeps more than "
                    "nine decimals"
                )
                assert not (
                    value == 0.0 and math.copysign(1.0, value) < 0.0
                ), "negative zero was published"
        for value in report["provenance"].values():
            assert type(value) is int


def test_unusable_reference_lane_leaves_the_previous_pair_untouched():
    """A run that cannot normalize publishes nothing and disturbs nothing."""
    good, good_state = calibrate("hv-norm-b")
    keep_report = REPORT.read_bytes()
    keep_state = STATE.read_bytes()

    listing = ["night_a.pmw2", "night_m.pmw2", "night_z.pmw2"]
    unfitted = next(
        row["lane_id"]
        for row in ref.contract_gain_table(ENV, "hv-raw-a")["lanes"]
        if row["status"] != "ok"
    )

    for reference in (unfitted, 4242):
        original = PROFILES.read_bytes()
        try:
            body = (
                "\n[vfy-badref]\n"
                "shards = [" + ", ".join(f'"{item}"' for item in listing) + "]\n"
                f"reference_lane = {reference}\n"
            )
            PROFILES.write_bytes(original + body.encode("utf-8"))
            finished = run_calibrate("vfy-badref")
        finally:
            PROFILES.write_bytes(original)

        assert finished.returncode == 1, (
            f"reference lane {reference} is unusable but the run succeeded"
        )
        assert finished.stderr.strip(), "the reason must reach standard error"
        assert REPORT.read_bytes() == keep_report
        assert STATE.read_bytes() == keep_state
        assert stray_temporaries() == []

    assert load_json(REPORT) == good
    assert load_json(STATE) == good_state


def test_doomed_state_path_writes_neither_artifact():
    """The pair is transactional: a doomed second write must not publish the first."""
    unwritable = STATE.parent / ("s" * 300 + ".json")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        unwritable.write_bytes(b"")
    except OSError:
        pass
    else:
        unwritable.unlink()
        pytest.skip("this filesystem accepts arbitrarily long file names")

    calibrate("hv-norm-b")
    keep_report = REPORT.read_bytes()
    keep_state = STATE.read_bytes()

    finished = run_calibrate("hv-raw-a", state=unwritable)
    assert finished.returncode == 1, "an impossible state path must fail the run"
    assert REPORT.read_bytes() == keep_report, (
        "the report was replaced even though the state could not be written"
    )
    assert STATE.read_bytes() == keep_state
    assert stray_temporaries() == [], "a failed write left a temporary file behind"


def test_stale_artifacts_are_replaced_and_missing_directories_recreated():
    """Both artifacts regenerate from the shards, whatever is on disk first."""
    expected = ref.contract_gain_table(ENV, "hv-raw-a")

    reset_artifacts()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"schema_version": 1, "lanes": []}), encoding="utf-8")
    STATE.write_text(json.dumps({"lane_count": 0}), encoding="utf-8")
    finished = run_calibrate("hv-raw-a")
    assert finished.returncode == 0, finished.stderr
    from_stale = load_json(REPORT)
    assert_report_matches(from_stale, expected)
    assert stray_temporaries() == []

    reset_artifacts()
    assert not REPORT.parent.exists()
    finished = run_calibrate("hv-raw-a")
    assert finished.returncode == 0, finished.stderr
    from_empty = load_json(REPORT)
    assert from_empty == from_stale, (
        "the published table depends on what was already on disk"
    )


def test_artifacts_are_utf8_json_with_two_space_indentation():
    """The files on disk follow the documented rendering, not the digest encoding."""
    calibrate("hv-neg-edge-d")
    for path in (REPORT, STATE):
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n")
        text = raw.decode("utf-8")
        assert text.splitlines()[1].startswith('  "'), (
            f"{path.name} is not indented with two spaces"
        )
        assert json.loads(text) is not None


@pytest.mark.skipif(not IN_CONTAINER, reason="default paths only exist in the image")
def test_default_artifact_paths_are_used_when_no_flags_are_given():
    """Invoked without flags the tool writes the two documented locations."""
    reset_artifacts()
    finished = run_calibrate("hv-raw-a", report=None, state=None)
    assert finished.returncode == 0, finished.stderr
    assert Path("/app/output/hv_gain_table.json").is_file()
    assert Path("/app/state/hv_replay_ledger.json").is_file()


def test_usage_exit_codes():
    """Help succeeds; a missing or unknown subcommand does not."""
    helped = run_calibrate("", argv=["--help"])
    assert helped.returncode == 0
    assert helped.stdout.strip()

    bare = run_calibrate("", argv=[])
    assert bare.returncode == 1

    unknown = run_calibrate("", argv=["reduce", "hv-raw-a"])
    assert unknown.returncode == 1

    nameless = run_calibrate("", argv=["calibrate"])
    assert nameless.returncode == 1


# ==========================================================================
# Suite integrity
# ==========================================================================

WORKSPACE_PACKAGES = frozenset(
    {
        "artiforge",
        "baseline",
        "chargegate",
        "coalesce",
        "fitlab",
        "fixturekit",
        "hvreduce",
        "importlib",
        "pedtrack",
        "pmwio",
        "qualitygate",
        "reducectl",
    }
)

PATH_MUTATORS = frozenset({"append", "insert", "extend"})


def imported_roots(tree: ast.AST) -> set[str]:
    """Top-level module names a parsed Python source imports."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def mutates_import_path(tree: ast.AST) -> bool:
    """True when the source calls ``sys.path.append`` or a sibling."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in PATH_MUTATORS:
            continue
        inner = node.value
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == "path"
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "sys"
        ):
            return True
    return False


def test_the_suite_never_imports_the_workspace_under_test():
    """The expected numbers must come from an independent implementation."""
    here = Path(__file__).resolve().parent
    for name in ("ref_eval.py", "test_outputs.py"):
        tree = ast.parse((here / name).read_text(encoding="utf-8"))
        borrowed = imported_roots(tree) & WORKSPACE_PACKAGES
        assert not borrowed, f"{name} reaches into the workspace via {sorted(borrowed)}"
        assert not mutates_import_path(tree), (
            f"{name} extends the import path to reach the workspace"
        )
