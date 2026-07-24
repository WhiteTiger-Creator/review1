"""Behavioral verifier for reconcile-oci-layer-store-after-interrupted-gc."""

import json
import subprocess
from pathlib import Path


def test_output_contract_smoke() -> None:
    """Inventory reports use schema version 1 and required top-level sections."""
    path = Path("/output/store-inventory.json")
    assert path.is_file(), "missing required output: /output/store-inventory.json"
    inventory = json.loads(path.read_text(encoding="utf-8"))

    assert inventory.get("schema_version") == 1
    assert inventory.get("status") in ("ok", "rejected", "partial")
    for key in ("images", "blobs", "snapshots", "leases", "quarantine", "gc"):
        assert key in inventory
    assert inventory["gc"]["pending"] == sorted(inventory["gc"]["pending"])


def test_run_result_contract_smoke() -> None:
    """Run-image results expose status, image name, and probe payload."""
    path = Path("/output/run-result.json")
    assert path.is_file(), "missing required output: /output/run-result.json"
    result = json.loads(path.read_text(encoding="utf-8"))

    assert result.get("status") in ("ok", "failed")
    assert isinstance(result.get("image"), str)
    if result.get("status") == "ok":
        assert result["rootfs_probe"]["exit_code"] == 0


def test_environment_workspace_available() -> None:
    """Confirm the task environment workspace is mounted before grading."""
    proc = subprocess.run(
        ["bash", "-lc", "cd /app/environment 2>/dev/null || cd /app && test -f Cargo.toml"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mint_verifier_behavioral_suite() -> None:
    """Grading reruns documented mint-cli workflows via the protected verifier driver."""
    script = Path(__file__).resolve().parent / "run_verifier.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "PASS clean_inspect" in output
