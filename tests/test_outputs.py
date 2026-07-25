from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from case_builder import make_case

APP_INPUT = Path("/app/task_file/input_data")
APP_OUTPUT = Path("/app/task_file/calibration")
APP_SOURCE = Path("/app/hall_transport.c")

if APP_INPUT.exists():
    INPUT_DIR = APP_INPUT
    OUTPUT_DIR = APP_OUTPUT
    SOURCE_PATH = APP_SOURCE
    TASK_FILE = Path("/app/task_file")
else:
    ROOT = Path(__file__).resolve().parents[1]
    INPUT_DIR = ROOT / "environment" / "task_file" / "input_data"
    OUTPUT_DIR = ROOT / "environment" / "task_file" / "calibration"
    SOURCE_PATH = ROOT / "solution" / "hall_transport.c"
    TASK_FILE = ROOT / "environment" / "task_file"

SPEC_SHA256 = "af520a8a1f5aa78662dc409c0989dba6af24e89475071142bf0f1bc602d283f0"
MODEL_SHA256 = "5853eac6f3b7f89b541f3bde54ae8f513c035544d2dac9bee67ca03b29185328"
PUBLIC_INPUT_SHA256 = {
    "carriers.csv": "0fcfff98ed9a70acb2607b3f106a524d3573607e0bb6940641e8d1887e45654b",
    "case_config.csv": "5a9362d3bd71da942384e85f50c7bd48ca71a463e0e4f91876584d6d444ec4ab",
    "input_hashes.json": "5a50ba2aaf1a9a393899710e14cf72a2b3e7308aa55ba1bdd7a492486f00bc5c",
    "observations.csv": "fd03429572661aae688c14fcc46c0878666d2604dfd8c2582db458d87ed7c8d3",
    "prior_flags.csv": "5cae1ee628e073c240fcfdb8e22281d91fbb2d1b6e987802820467ba2b6d7d37",
    "runs.csv": "4a33aaa2a81e060a40f9c5d37b7f37af03f5af8f6fd0b2397b9637fb3a7eea5a",
}
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
OUTPUT_NAMES = [
    "transport_parameters.json",
    "observation_residuals.jsonl",
    "transport_summary.json",
]

model_spec = importlib.util.spec_from_file_location(
    "transport_model", TASK_FILE / "transport_model.py"
)
assert model_spec and model_spec.loader
model = importlib.util.module_from_spec(model_spec)
model_spec.loader.exec_module(model)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fields: list[str], values: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)


def finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def six_decimal_number(value: object) -> bool:
    return finite_number(value) and float(value) == round(float(value), 6)


def parse_parameters(output_dir: Path, archive: dict) -> dict:
    payload = json.loads((output_dir / "transport_parameters.json").read_text())
    assert set(payload) == {
        "reference",
        "rounding",
        "carriers",
        "runs",
        "constraints",
    }
    assert payload["reference"] == "carrier input order and run input order"
    assert payload["rounding"] == ROUNDING
    assert len(payload["carriers"]) == len(archive["carriers"])
    assert len(payload["runs"]) == len(archive["runs"])

    carriers = {}
    carrier_keys = {
        "carrier_id",
        "band_index",
        "charge_sign",
        "density_1e22_m3",
        "mobility_cm2_vs",
        "activation_mev",
        "alpha",
    }
    field_map = {
        "density_1e22_m3": (
            "density_min_1e22_m3",
            "density_max_1e22_m3",
        ),
        "mobility_cm2_vs": ("mobility_min_cm2_vs", "mobility_max_cm2_vs"),
        "activation_mev": ("activation_min_mev", "activation_max_mev"),
        "alpha": ("alpha_min", "alpha_max"),
    }
    for actual, expected in zip(
        payload["carriers"], archive["carriers"], strict=True
    ):
        assert set(actual) == carrier_keys
        assert actual["carrier_id"] == expected["carrier_id"]
        assert type(actual["band_index"]) is int
        assert actual["band_index"] == expected["band_index"]
        assert type(actual["charge_sign"]) is int
        assert actual["charge_sign"] == expected["charge_sign"]
        values = {}
        for field, (minimum, maximum) in field_map.items():
            assert six_decimal_number(actual[field])
            value = float(actual[field])
            assert expected[minimum] <= value <= expected[maximum]
            values[field] = value
        carriers[expected["carrier_id"]] = values

    runs = {}
    run_keys = {
        "run_id",
        "temperature_k",
        "field_scale",
        "longitudinal_offset_uohm_m",
        "hall_offset_uohm_m",
    }
    run_field_map = {
        "field_scale": ("field_scale_min", "field_scale_max"),
        "longitudinal_offset_uohm_m": (
            "longitudinal_offset_min_uohm_m",
            "longitudinal_offset_max_uohm_m",
        ),
        "hall_offset_uohm_m": (
            "hall_offset_min_uohm_m",
            "hall_offset_max_uohm_m",
        ),
    }
    for actual, expected in zip(payload["runs"], archive["runs"], strict=True):
        assert set(actual) == run_keys
        assert actual["run_id"] == expected["run_id"]
        assert six_decimal_number(actual["temperature_k"])
        assert float(actual["temperature_k"]) == pytest.approx(
            expected["temperature_k"], abs=5.1e-7
        )
        values = {}
        for field, (minimum, maximum) in run_field_map.items():
            assert six_decimal_number(actual[field])
            value = float(actual[field])
            assert expected[minimum] <= value <= expected[maximum]
            values[field] = value
        runs[expected["run_id"]] = values

    metrics = model.constraint_metrics(archive, carriers, runs)
    assert set(payload["constraints"]) == set(metrics)
    for key, expected in metrics.items():
        assert six_decimal_number(payload["constraints"][key])
        assert float(payload["constraints"][key]) == pytest.approx(
            expected, abs=5.1e-7
        )
    cfg = archive["cfg"]
    assert metrics["charge_imbalance"] <= cfg["max_charge_imbalance"] + 1.0e-12
    assert (
        cfg["total_density_min_1e22_m3"]
        <= metrics["total_density_1e22_m3"]
        <= cfg["total_density_max_1e22_m3"]
    )
    assert (
        metrics["minimum_conductivity_share"]
        >= cfg["min_conductivity_share"] - 1.0e-12
    )
    assert (
        metrics["minimum_mobility_ratio"]
        >= cfg["min_mobility_ratio"] - 1.0e-12
    )
    assert (
        metrics["maximum_activation_step_mev"]
        <= cfg["max_activation_step_mev"] + 1.0e-12
    )
    assert (
        metrics["maximum_field_scale_step"]
        <= cfg["max_field_scale_step"] + 1.0e-12
    )
    assert (
        abs(metrics["mean_longitudinal_offset_uohm_m"])
        <= cfg["max_mean_longitudinal_offset_uohm_m"] + 1.0e-12
    )
    assert (
        abs(metrics["mean_hall_offset_uohm_m"])
        <= cfg["max_mean_hall_offset_uohm_m"] + 1.0e-12
    )
    return {"carriers": carriers, "runs": runs, "metrics": metrics}


def validate_residuals(output_dir: Path, archive: dict, result: dict) -> None:
    actual = [
        json.loads(line)
        for line in (output_dir / "observation_residuals.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    ordered = sorted(
        enumerate(archive["observations"]), key=lambda pair: pair[1]["observation_id"]
    )
    expected_keys = {
        "observation_id",
        "run_id",
        "field_t",
        "modeled_longitudinal_uohm_m",
        "observed_longitudinal_uohm_m",
        "longitudinal_residual_sigma",
        "modeled_hall_uohm_m",
        "observed_hall_uohm_m",
        "hall_residual_sigma",
        "findings",
    }
    assert len(actual) == len(ordered)
    for row, (index, source) in zip(actual, ordered, strict=True):
        assert set(row) == expected_keys
        assert row["observation_id"] == source["observation_id"]
        assert row["run_id"] == source["run_id"]
        for field in (
            "field_t",
            "modeled_longitudinal_uohm_m",
            "observed_longitudinal_uohm_m",
            "longitudinal_residual_sigma",
            "modeled_hall_uohm_m",
            "observed_hall_uohm_m",
            "hall_residual_sigma",
        ):
            assert six_decimal_number(row[field])
        assert float(row["field_t"]) == pytest.approx(source["field_t"], abs=5.1e-7)
        assert float(row["modeled_longitudinal_uohm_m"]) == pytest.approx(
            result["modeled"][index][0], abs=5.1e-7
        )
        assert float(row["modeled_hall_uohm_m"]) == pytest.approx(
            result["modeled"][index][1], abs=5.1e-7
        )
        assert float(row["observed_longitudinal_uohm_m"]) == pytest.approx(
            source["observed_longitudinal_uohm_m"], abs=5.1e-7
        )
        assert float(row["observed_hall_uohm_m"]) == pytest.approx(
            source["observed_hall_uohm_m"], abs=5.1e-7
        )
        replay_longitudinal = (
            float(row["modeled_longitudinal_uohm_m"])
            - source["observed_longitudinal_uohm_m"]
        ) / source["sigma_longitudinal_uohm_m"]
        replay_hall = (
            float(row["modeled_hall_uohm_m"]) - source["observed_hall_uohm_m"]
        ) / source["sigma_hall_uohm_m"]
        assert min(
            abs(
                float(row["longitudinal_residual_sigma"])
                - result["residuals"][index][0]
            ),
            abs(float(row["longitudinal_residual_sigma"]) - replay_longitudinal),
        ) <= 1.0e-5
        assert min(
            abs(float(row["hall_residual_sigma"]) - result["residuals"][index][1]),
            abs(float(row["hall_residual_sigma"]) - replay_hall),
        ) <= 1.0e-5
        assert row["findings"] == result["findings"][index]


def validate_summary(
    output_dir: Path, archive: dict, parameters: dict, result: dict
) -> None:
    payload = json.loads((output_dir / "transport_summary.json").read_text())
    expected_keys = {
        "carrier_count",
        "run_count",
        "observations",
        "scored_observations",
        "clean_observations",
        "combined_rms",
        "longitudinal_rms",
        "hall_rms",
        "residual_p90",
        "clean_fraction",
        "charge_imbalance",
        "total_density_1e22_m3",
        "minimum_conductivity_share",
        "minimum_mobility_ratio",
        "maximum_activation_step_mev",
        "maximum_field_scale_step",
        "mean_longitudinal_offset_uohm_m",
        "mean_hall_offset_uohm_m",
        "finding_counts",
    }
    assert set(payload) == expected_keys
    counts = {
        "carrier_count": len(archive["carriers"]),
        "run_count": len(archive["runs"]),
        "observations": len(archive["observations"]),
        "scored_observations": result["scored"],
        "clean_observations": result["clean"],
    }
    for key, expected in counts.items():
        assert type(payload[key]) is int and payload[key] == expected
    metrics = {
        "combined_rms": result["combined_rms"],
        "longitudinal_rms": result["longitudinal_rms"],
        "hall_rms": result["hall_rms"],
        "residual_p90": result["residual_p90"],
        "clean_fraction": result["clean_fraction"],
        **parameters["metrics"],
    }
    for key, expected in metrics.items():
        assert six_decimal_number(payload[key])
        assert float(payload[key]) == pytest.approx(expected, abs=5.1e-7)
    assert set(payload["finding_counts"]) == set(FINDINGS)
    assert payload["finding_counts"] == result["finding_counts"]


def validate_calibration(input_dir: Path, output_dir: Path) -> dict:
    archive = model.load_archive(input_dir)
    parameters = parse_parameters(output_dir, archive)
    result = model.evaluate(input_dir, output_dir)
    validate_residuals(output_dir, archive, result)
    validate_summary(output_dir, archive, parameters, result)
    cfg = archive["cfg"]
    assert result["combined_rms"] <= cfg["combined_rms_max"] + 1.0e-12
    assert (
        result["longitudinal_rms"] <= cfg["longitudinal_rms_max"] + 1.0e-12
    )
    assert result["hall_rms"] <= cfg["hall_rms_max"] + 1.0e-12
    assert result["residual_p90"] <= cfg["residual_p90_max"] + 1.0e-12
    assert result["clean_fraction"] >= cfg["min_clean_fraction"] - 1.0e-12
    return {"archive": archive, "parameters": parameters, "result": result}


def run_solver(
    binary: Path,
    input_dir: Path,
    output_dir: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_NAMES:
        (output_dir / name).unlink(missing_ok=True)
    return subprocess.run(
        [str(binary), str(input_dir), str(output_dir)],
        check=check,
        text=True,
        capture_output=True,
        timeout=90,
    )


@pytest.fixture(scope="session")
def rebuilt_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the submitted source cleanly and reject process delegation."""
    build_dir = tmp_path_factory.mktemp("native-build")
    if not SOURCE_PATH.exists():
        pytest.skip("hall_transport.c is missing")
    source = SOURCE_PATH.read_text()
    assert re.search(r"\bint\s+main\s*\(", source)
    binary = build_dir / "hall_transport"
    completed = subprocess.run(
        [
            "cc",
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-o",
            str(binary),
            str(SOURCE_PATH),
            "-lm",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert completed.stderr == "", f"compiler warnings are not allowed: {completed.stderr}"
    symbols = subprocess.run(
        ["nm", "-u", str(binary)],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    forbidden = re.compile(
        r"\b(system|popen|fork|vfork|clone|execl|execle|execlp|execv|execve|"
        r"execvp|posix_spawn|posix_spawnp)\b"
    )
    assert not forbidden.search(symbols), "the native program links a process API"
    return binary


class TestInputIntegrity:
    def test_public_archive_hashes(self):
        """The public transport archive remains unchanged."""
        manifest = json.loads((INPUT_DIR / "input_hashes.json").read_text())
        assert set(manifest) == set(PUBLIC_INPUT_SHA256) - {"input_hashes.json"}
        for name, expected in PUBLIC_INPUT_SHA256.items():
            assert sha256(INPUT_DIR / name) == expected, f"{name} hash drifted"

    def test_public_contract_hashes(self):
        """The public specification and numeric model are immutable."""
        assert sha256(TASK_FILE / "transport_spec.md") == SPEC_SHA256
        assert sha256(TASK_FILE / "transport_model.py") == MODEL_SHA256


class TestSubmittedCalibration:
    def test_required_native_source_exists(self):
        """The required native C source is present at the documented path."""
        assert SOURCE_PATH.exists(), "hall_transport.c is missing"

    @pytest.mark.parametrize("filename", OUTPUT_NAMES)
    def test_required_outputs_exist(self, filename):
        """Each named output exists and is nonempty."""
        path = OUTPUT_DIR / filename
        assert path.exists() and path.stat().st_size > 0

    def test_public_calibration_replays_and_meets_every_gate(self):
        """Canonical public parameters satisfy all physical and quality gates."""
        validate_calibration(INPUT_DIR, OUTPUT_DIR)

    def test_supplied_priors_are_not_a_solution(self):
        """The realistic priors miss the public residual-quality surface."""
        archive = model.load_archive(INPUT_DIR)
        carriers = {
            row["carrier_id"]: {
                "density_1e22_m3": row["prior_density_1e22_m3"],
                "mobility_cm2_vs": row["prior_mobility_cm2_vs"],
                "activation_mev": row["prior_activation_mev"],
                "alpha": row["prior_alpha"],
            }
            for row in archive["carriers"]
        }
        runs = {
            row["run_id"]: {
                "field_scale": row["prior_field_scale"],
                "longitudinal_offset_uohm_m": row[
                    "prior_longitudinal_offset_uohm_m"
                ],
                "hall_offset_uohm_m": row["prior_hall_offset_uohm_m"],
            }
            for row in archive["runs"]
        }
        residuals = []
        for observation in archive["observations"]:
            if (
                observation["use_flag"] == 0
                or observation["observation_id"] in archive["prior_flags"]
            ):
                continue
            longitudinal, hall = model.modeled_pair(
                archive, carriers, runs, observation
            )
            residuals.append(
                (
                    (longitudinal - observation["observed_longitudinal_uohm_m"])
                    / observation["sigma_longitudinal_uohm_m"],
                    (hall - observation["observed_hall_uohm_m"])
                    / observation["sigma_hall_uohm_m"],
                )
            )
        combined = math.sqrt(
            sum(left * left + right * right for left, right in residuals)
            / (2 * len(residuals))
        )
        assert combined > archive["cfg"]["combined_rms_max"]


class TestNativeGeneralization:
    def test_rebuilt_source_handles_public_archive(
        self, rebuilt_binary: Path, tmp_path: Path
    ):
        """A clean native rebuild regenerates a valid public calibration."""
        input_copy = tmp_path / "input"
        output_dir = tmp_path / "output"
        shutil.copytree(INPUT_DIR, input_copy)
        run_solver(rebuilt_binary, input_copy, output_dir)
        validate_calibration(input_copy, output_dir)
        wrong_args = subprocess.run(
            [str(rebuilt_binary)], text=True, capture_output=True
        )
        assert wrong_args.returncode != 0

    def test_runtime_starts_no_other_process(
        self, rebuilt_binary: Path, tmp_path: Path
    ):
        """Process tracing permits only the initial exec of the solver."""
        input_copy = tmp_path / "input"
        output_dir = tmp_path / "output"
        trace_path = tmp_path / "process.trace"
        shutil.copytree(INPUT_DIR, input_copy)
        output_dir.mkdir()
        completed = subprocess.run(
            [
                "strace",
                "-f",
                "-qq",
                "-e",
                "trace=process",
                "-o",
                str(trace_path),
                str(rebuilt_binary),
                str(input_copy),
                str(output_dir),
            ],
            text=True,
            capture_output=True,
            timeout=90,
        )
        assert completed.returncode == 0, completed.stderr
        trace = trace_path.read_text()
        assert not re.search(r"\b(clone|clone3|fork|vfork)\(", trace)
        assert len(re.findall(r"\bexecve\(", trace)) <= 1
        validate_calibration(input_copy, output_dir)

    @pytest.mark.parametrize("mode", list(range(1, 17)))
    def test_compatible_scientific_matrix(
        self, rebuilt_binary: Path, tmp_path: Path, mode: int
    ):
        """The same C solver handles every documented scientific regime."""
        input_dir = tmp_path / f"case-{mode}"
        output_dir = tmp_path / f"output-{mode}"
        make_case(mode, input_dir)
        run_solver(rebuilt_binary, input_dir, output_dir)
        validate_calibration(input_dir, output_dir)

    def test_outputs_respond_to_changed_scientific_inputs(
        self, rebuilt_binary: Path, tmp_path: Path
    ):
        """Changed carrier topology and temperature coverage change the fit."""
        first_input = tmp_path / "first-input"
        second_input = tmp_path / "second-input"
        first_output = tmp_path / "first-output"
        second_output = tmp_path / "second-output"
        make_case(3, first_input)
        make_case(14, second_input)
        run_solver(rebuilt_binary, first_input, first_output)
        run_solver(rebuilt_binary, second_input, second_output)
        first = validate_calibration(first_input, first_output)
        second = validate_calibration(second_input, second_output)
        assert len(first["archive"]["carriers"]) != len(second["archive"]["carriers"])
        assert first["parameters"]["carriers"] != second["parameters"]["carriers"]

    def test_infeasible_archive_leaves_no_outputs(
        self, rebuilt_binary: Path, tmp_path: Path
    ):
        """An impossible configured density interval fails atomically."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        make_case(5, input_dir)
        carrier_rows = rows(input_dir / "carriers.csv")
        impossible_minimum = (
            sum(float(row["density_max_1e22_m3"]) for row in carrier_rows) + 1.0
        )
        config_rows = rows(input_dir / "case_config.csv")
        for row in config_rows:
            if row["key"] == "total_density_min_1e22_m3":
                row["value"] = f"{impossible_minimum:.12f}"
        write_rows(input_dir / "case_config.csv", ["key", "value"], config_rows)
        output_dir.mkdir()
        for name in OUTPUT_NAMES:
            (output_dir / name).write_text("stale\n")
        completed = run_solver(
            rebuilt_binary, input_dir, output_dir, check=False
        )
        assert completed.returncode != 0
        assert all(not (output_dir / name).exists() for name in OUTPUT_NAMES)
