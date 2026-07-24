import os
import subprocess
from pathlib import Path

import pytest

APP_DIR = Path(os.environ.get("APP_DIR", "/app/environment"))
TEST_DIR = Path(os.environ.get("TEST_DIR", "/tests"))
CASES = (
    "constant-density",
    "density-ramp",
    "layer-boundary",
    "continuation",
    "energy-order",
    "physical-inputs",
    "preservation",
    "terminal",
    "generated",
    "earth-reference",
)


@pytest.fixture(scope="session")
def binaries(tmp_path_factory):
    if APP_DIR == Path("/app/environment"):
        subprocess.run(["go", "-C", "/app/environment", "test", "./..."], check=True)
    else:
        subprocess.run(["go", "-C", str(APP_DIR), "test", "./..."], check=True)
    build_dir = tmp_path_factory.mktemp("neutrino_bins")
    solver = build_dir / "nuosc"
    checker = build_dir / Path(__file__).stem
    subprocess.run(
        ["go", "-C", str(APP_DIR), "build", "-trimpath", "-o", str(solver), "./cmd/nuosc"],
        check=True,
    )
    subprocess.run(
        ["go", "-C", str(TEST_DIR), "build", "-trimpath", "-o", str(checker), "."],
        check=True,
    )
    return solver, checker


def _run_case(binaries, case_index):
    solver, checker = binaries
    case_name = CASES[case_index]
    completed = subprocess.run(
        [str(checker), "-bin", str(solver), "-scenario", case_name],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == f"ok {case_name}\n"
    assert completed.stderr == ""


def test_constant_density(binaries):
    """Compare constant-density flavor evolution with an independent reference."""
    _run_case(binaries, 0)


def test_density_ramp(binaries):
    """Verify endpoint-bounded subdivision and midpoint matter evolution."""
    _run_case(binaries, 1)


def test_layer_boundary(binaries):
    """Verify physical-layer stopping lands on the planned numerical boundary."""
    _run_case(binaries, 2)


def test_continuation_equivalence(binaries):
    """Match uninterrupted propagation after an interior-substep continuation."""
    _run_case(binaries, 3)


def test_energy_order(binaries):
    """Preserve physical results when the configured energy grid is permuted."""
    _run_case(binaries, 4)


def test_physical_inputs(binaries):
    """Reject nonphysical matter inputs and inconsistent continuation histories."""
    _run_case(binaries, 5)


def test_result_preservation(binaries):
    """Preserve the prior scientific result set when publication cannot complete."""
    _run_case(binaries, 6)


def test_terminal_continuation(binaries):
    """Keep terminal continuations deterministic with an empty trajectory segment."""
    _run_case(binaries, 7)


def test_generated_mantles(binaries):
    """Evaluate generated mantle ramps and continuation boundaries."""
    _run_case(binaries, 8)


def test_earth_reference(binaries):
    """Exercise the bundled Earth profile through the documented default paths."""
    _run_case(binaries, 9)
