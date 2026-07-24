"""
Pytest suite for the RFC 6962 Certificate Transparency log auditor.
Tests are driven by the compiled Go test runner binary at /tmp/test_ct.
"""

import subprocess
import pytest


def run(test_name: str, race: bool = False, timeout: int = 30) -> subprocess.CompletedProcess:
    binary = "/tmp/test_ct_race" if race else "/tmp/test_ct"
    return subprocess.run(
        [binary, test_name],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.timeout(15)
def test_leaf_hash():
    """RFC 6962 §2.1: HashLeaf must produce SHA-256(0x00 || data), not SHA-256(data)."""
    r = run("leaf_hash")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "LEAF_HASH_OK" in r.stdout


@pytest.mark.timeout(20)
def test_inclusion_proof():
    """RFC 6962 §2.1.1: VerifyInclusion must correctly order siblings
    (even index = left child, sibling on right) for a 4-leaf tree."""
    r = run("inclusion_proof")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "INCLUSION_PROOF_OK" in r.stdout


@pytest.mark.timeout(20)
def test_sct_signing_format():
    """RFC 6962 §3.2: SCT signing input must include Version | SignatureType | Timestamp | ...
    Omitting SignatureType causes ECDSA verification to fail against correct signatures."""
    r = run("sct_signing_format")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "SCT_SIGNING_FORMAT_OK" in r.stdout


@pytest.mark.timeout(15)
def test_timestamp_validation():
    """ValidateSCT must reject future-dated SCTs (beyond clock skew) and accept
    valid SCTs with timestamps in the past (recent and historical)."""
    r = run("timestamp_validation")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "TIMESTAMP_VALIDATION_OK" in r.stdout


@pytest.mark.timeout(15)
def test_consistency_equal_size():
    """VerifyConsistency must return error when snapshot1==snapshot2 but roots differ,
    and succeed when both size and root match. Skipping this check enables root forgery."""
    r = run("consistency_equal_size")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "CONSISTENCY_EQUAL_SIZE_OK" in r.stdout


@pytest.mark.timeout(25)
def test_batch_race_correctness():
    """BatchVerifier.VerifyBatch must verify all SCTs correctly when run with
    10 concurrent goroutines — detects corrupted digests from shared hash state."""
    r = run("batch_race", timeout=20)
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "BATCH_RACE_OK" in r.stdout


@pytest.mark.timeout(25)
def test_batch_race_detector():
    """Go race detector must not report DATA RACE during concurrent BatchVerify calls."""
    r = run("batch_race", race=True, timeout=20)
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "WARNING: DATA RACE" not in r.stderr, (
        f"Data race detected:\n{r.stderr}"
    )
    assert "BATCH_RACE_OK" in r.stdout


@pytest.mark.timeout(15)
def test_malformed_entry():
    """ParseLogEntry must return an error (not panic) when the extensions length
    field in a log entry exceeds the remaining buffer length."""
    r = run("malformed_entry")
    assert r.returncode == 0, f"stdout: {r.stdout}\nstderr: {r.stderr}"
    assert "MALFORMED_ENTRY_OK" in r.stdout
