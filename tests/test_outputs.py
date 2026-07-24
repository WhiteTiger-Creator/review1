"""Tests for TUF metadata rollout verifier."""

import hashlib
import json
import subprocess
from pathlib import Path

BINARY = "/app/bin/tuf-rollout-verifier"
REPORT = "/app/output/rollout_report.json"
CONFIG = "/app/config/trust_policy.json"
LANES = "/app/config/rollout_lanes.json"
REPO = Path("/app/data/repo")
EXPECTED = Path("/tests/expected_report.json")

POLICY_SHA256 = "710fa98a5ee35ed64269427bae172c52ca8217681a55ed156ba9945beed62534"
LANES_SHA256 = "59d5ce992715a1fc2f70d4b7e1ee0d25139be9f1b13b56da9ab81043b62a96ae"
METADATA_SHA256 = {
    "root.json": "ad6e8e5e817dcc652eb1f040a2ed6e331ed70f685a997e03ed699c7b9e48d9e7",
    "timestamp.json": "674cc5b2acfe70c206f755292241db32f482d90ba95252e2da5c6135cade340c",
    "snapshot.json": "67d517f9f9f596056b66c756630ed84e4aa66a75f306c213ed56db90f0931ba7",
    "targets.json": "d60fa32daab4bdb83a643651eb15251c3ffd23fdba27f7c76cab980ace71ec25",
}
TARGET_SHA256 = {
    "targets/bundle_eta.tar": "22529ebd2b1fb4595fbde63159ba47080c8a011b45faf4a20b0422f11917fba6",
    "targets/config_delta.json": "776e862bfa3d792e54e76b7c75bcca7ce80f81c78556290a63a39b29c62e4a7e",
    "targets/config_epsilon.json": "2ec98bb91bc9c3fce0d03cae58f89fc19005f7871c211bb1423e2132e7731bc9",
    "targets/firmware_alpha.bin": "bc2720f9adaa8c3116af62db9f393e1350e2804ff1d69c22c03067c8bd04b883",
    "targets/firmware_beta.bin": "9db9199f01eed3251f734a4d244026a04646d1a9f1c944b2e78ab4735ed727a7",
    "targets/firmware_gamma.bin": "f635377ec29437e1710e9cfbd0c93e87aa5022174cadb1939904ed373bbf939e",
    "targets/patch_zeta.bin": "655e7a88a76f0e25bd45f3345ea9e46eafa8dc2c18e3dd1c807b386af4331183",
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_report() -> dict:
    with open(REPORT) as f:
        return json.load(f)


def load_expected() -> dict:
    return load_json(EXPECTED)


def target_by_path(report: dict, path: str) -> dict:
    for t in report["targets"]:
        if t["path"] == path:
            return t
    raise KeyError(path)


def role_by_name(report: dict, name: str) -> dict:
    for r in report["roles"]:
        if r["role"] == name:
            return r
    raise KeyError(name)


def seal_report_digest(roles: list[dict], targets: list[dict]) -> str:
    payload = {"roles": roles, "targets": targets}
    return sha256_hex(canonical_json(payload).encode("utf-8"))


class TestReportShape:
    def test_report_exists(self) -> None:
        """The verifier must write the rollout report artifact."""
        assert Path(REPORT).exists()

    def test_report_schema(self) -> None:
        """Config, roles, targets, and summary must expose the contract fields."""
        run_report = load_report()
        cfg = run_report["config"]
        for k in (
            "spec_version",
            "reference_time",
            "require_target_hashes",
            "freeze_window_start",
            "freeze_window_end",
            "blocked_lanes",
            "allowed_lanes",
        ):
            assert k in cfg
        assert len(run_report["roles"]) == 4
        for r in run_report["roles"]:
            for k in ("role", "version", "status", "signatures_ok", "signatures_required", "expired"):
                assert k in r
        assert len(run_report["targets"]) >= 5
        for t in run_report["targets"]:
            for k in (
                "path",
                "length",
                "sha256",
                "hash_match",
                "lane",
                "lane_blocked",
                "freeze_blocked",
                "rollout_eligible",
                "min_snapshot_version",
                "max_snapshot_version",
                "active_snapshot_version",
            ):
                assert k in t
        summ = run_report["summary"]
        for k in (
            "roles_valid",
            "roles_total",
            "targets_listed",
            "targets_hash_ok",
            "targets_rollout_eligible",
            "targets_lane_blocked",
            "targets_freeze_blocked",
            "chain_intact",
            "report_digest",
        ):
            assert k in summ

    def test_config_lane_csv_sorted(self) -> None:
        """Config must echo blocked and allowed lanes as lexicographically sorted CSVs."""
        policy = load_json(Path(CONFIG))
        cfg = load_report()["config"]
        assert cfg["blocked_lanes"] == ",".join(sorted(policy["blocked_lanes"]))
        assert cfg["allowed_lanes"] == ",".join(sorted(policy["allowed_lanes"]))
        assert cfg["blocked_lanes"] == "canary,staging"
        assert cfg["allowed_lanes"] == "production,zebra"
        assert cfg["blocked_lanes"] != ",".join(policy["blocked_lanes"])
        assert cfg["allowed_lanes"] != ",".join(policy["allowed_lanes"])

    def test_role_order(self) -> None:
        """Roles must appear in root, timestamp, snapshot, targets order."""
        assert [r["role"] for r in load_report()["roles"]] == [
            "root",
            "timestamp",
            "snapshot",
            "targets",
        ]

    def test_target_paths_sorted(self) -> None:
        """Target entries must be ordered lexicographically by path."""
        paths = [t["path"] for t in load_report()["targets"]]
        assert paths == sorted(paths)


class TestGoldenParity:
    def test_full_report_matches_golden(self) -> None:
        """Settled report from the agent binary must match the sealed golden artifact."""
        assert load_report() == load_expected()

    def test_summary_rollups_internal_consistency(self) -> None:
        """Summary counters must equal aggregates over roles and targets."""
        run_report = load_report()
        summary = run_report["summary"]
        captures = run_report["targets"]
        roles = run_report["roles"]
        assert summary["roles_total"] == len(roles)
        assert summary["targets_listed"] == len(captures)
        assert summary["roles_valid"] == sum(1 for r in roles if r["status"] == "valid")
        assert summary["targets_hash_ok"] == sum(1 for t in captures if t["hash_match"])
        assert summary["targets_rollout_eligible"] == sum(
            1 for t in captures if t["rollout_eligible"]
        )
        assert summary["targets_lane_blocked"] == sum(1 for t in captures if t["lane_blocked"])
        assert summary["targets_freeze_blocked"] == sum(1 for t in captures if t["freeze_blocked"])
        assert summary["report_digest"] == seal_report_digest(roles, captures)


class TestBundledScenarios:
    def test_snapshot_requires_two_signatures(self) -> None:
        """Snapshot threshold two must be met with distinct valid keyids."""
        snap = role_by_name(load_report(), "snapshot")
        assert snap["signatures_required"] == 2
        assert snap["signatures_ok"] >= 2
        assert snap["status"] == "valid"

    def test_timestamp_duplicate_keyid_dedup(self) -> None:
        """Invalid earlier keyid entries must not block a later valid signature."""
        ts = role_by_name(load_report(), "timestamp")
        assert ts["signatures_ok"] == 1
        assert ts["status"] == "valid"
        ts_doc = load_json(REPO / "timestamp.json")
        assert len(ts_doc["signatures"]) >= 3

    def test_chain_intact(self) -> None:
        """Raw on-disk metadata bytes must keep the timestamp/snapshot/targets chain intact."""
        assert load_report()["summary"]["chain_intact"] is True

    def test_staging_lane_blocked(self) -> None:
        """Targets on blocked lanes must be lane_blocked and ineligible."""
        delta = target_by_path(load_report(), "targets/config_delta.json")
        assert delta["lane"] == "staging"
        assert delta["lane_blocked"] is True
        assert delta["rollout_eligible"] is False

    def test_allowlist_blocks_experimental(self) -> None:
        """Non-empty allowed_lanes must block targets whose lane is outside the allowlist."""
        eta = target_by_path(load_report(), "targets/bundle_eta.tar")
        assert eta["lane"] == "experimental"
        assert eta["lane_blocked"] is True
        assert eta["rollout_eligible"] is False

    def test_max_snapshot_blocks_zeta(self) -> None:
        """Targets whose max_snapshot_version is below active snapshot are ineligible."""
        zeta = target_by_path(load_report(), "targets/patch_zeta.bin")
        assert zeta["max_snapshot_version"] == 2
        assert zeta["rollout_eligible"] is False

    def test_min_snapshot_blocks_beta(self) -> None:
        """Targets whose min_snapshot_version exceeds active snapshot are ineligible."""
        beta = target_by_path(load_report(), "targets/firmware_beta.bin")
        assert beta["rollout_eligible"] is False

    def test_freeze_inactive_at_end_boundary(self) -> None:
        """Half-open freeze must stay inactive when reference_time equals freeze_window_end."""
        run_report = load_report()
        assert run_report["summary"]["targets_freeze_blocked"] == 0
        for t in run_report["targets"]:
            assert t["freeze_blocked"] is False


class TestIntegrity:
    def test_metadata_integrity_pinned(self) -> None:
        """Signed metadata must remain byte-identical to the pinned digests."""
        for name, expected in METADATA_SHA256.items():
            blob = (REPO / name).read_bytes()
            assert sha256_hex(blob) == expected, f"Modified {name}"

    def test_integrity_manifest_matches_pinned(self) -> None:
        """Repository integrity.json must still match the pinned metadata digests."""
        digests = load_json(REPO / "integrity.json")
        assert digests == METADATA_SHA256

    def test_policy_integrity(self) -> None:
        """Trust policy must remain unmodified."""
        digest = sha256_hex(Path(CONFIG).read_bytes())
        assert digest == POLICY_SHA256, f"trust_policy.json modified: {digest}"

    def test_lanes_integrity(self) -> None:
        """Lane map must remain unmodified."""
        digest = sha256_hex(Path(LANES).read_bytes())
        assert digest == LANES_SHA256, f"rollout_lanes.json modified: {digest}"

    def test_target_payload_integrity(self) -> None:
        """Target payload files under the repository must remain byte-identical."""
        for rel, expected in TARGET_SHA256.items():
            blob = (REPO / rel).read_bytes()
            assert sha256_hex(blob) == expected, f"Modified {rel}"

    def test_no_private_keys_in_image(self) -> None:
        """Agent image must not ship private signing material under config/keys."""
        keys_dir = Path("/app/config/keys")
        assert not keys_dir.exists() or not any(keys_dir.glob("*.pem"))

    def test_no_repo_generator_in_image(self) -> None:
        """Agent image must not ship a repository regenerator under /app/scripts."""
        assert not Path("/app/scripts/gen_repo.py").exists()


class TestBehavior:
    def test_deterministic_output(self) -> None:
        """Repeated verifier runs must produce identical reports."""
        subprocess.run([BINARY], cwd="/app", capture_output=True, check=True)
        first = load_report()
        subprocess.run([BINARY], cwd="/app", capture_output=True, check=True)
        second = load_report()
        assert first == second

    def test_modified_target_changes_hash_match(self) -> None:
        """Altering a target payload must clear hash_match and reduce targets_hash_ok."""
        orig = load_report()
        target = REPO / "targets/firmware_alpha.bin"
        backup = target.read_bytes()
        try:
            target.write_bytes(backup + b"x")
            subprocess.run([BINARY], cwd="/app", capture_output=True, check=True)
            modified = load_report()
        finally:
            target.write_bytes(backup)
            subprocess.run([BINARY], cwd="/app", capture_output=True, check=True)
        alpha = target_by_path(modified, "targets/firmware_alpha.bin")
        assert alpha["hash_match"] is False
        assert modified["summary"]["targets_hash_ok"] < orig["summary"]["targets_hash_ok"]
        assert load_report() == orig

    def test_help_flag(self) -> None:
        """--help must print usage, exit 0, and leave the report unchanged."""
        before = Path(REPORT).read_bytes()
        completed = subprocess.run(
            [BINARY, "--help"], cwd="/app", capture_output=True, text=True
        )
        assert completed.returncode == 0
        combined = (completed.stdout or "") + (completed.stderr or "")
        assert "Usage" in combined or "usage" in combined.lower()
        assert Path(REPORT).read_bytes() == before
