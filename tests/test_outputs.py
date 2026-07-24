"""Behavior tests for the robust vault quorum recovery checker."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
from itertools import combinations
import re
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BIN = APP / "bin" / "vaultquorum"
PRIME = 257


@pytest.fixture(scope="session", autouse=True)
def clean_build() -> None:
    """Rebuild the current Go package and verify that the reusable artifact is a Go ELF."""
    BIN.unlink(missing_ok=True)
    scripted = subprocess.run(
        ["/app/build.sh"], cwd=APP, text=True, capture_output=True, timeout=60
    )
    assert scripted.returncode == 0, scripted.stderr + scripted.stdout
    assert BIN.exists(), "build did not create /app/bin/vaultquorum"

    BIN.unlink()
    direct = subprocess.run(
        ["go", "build", "-trimpath", "-o", str(BIN), "."],
        cwd=APP,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert direct.returncode == 0, direct.stderr + direct.stdout
    assert os.access(BIN, os.X_OK), "vaultquorum is not executable"
    assert BIN.read_bytes()[:4] == b"\x7fELF", "build output is not an ELF binary"
    metadata = subprocess.run(
        ["go", "version", "-m", str(BIN)], text=True, capture_output=True, timeout=10
    )
    assert metadata.returncode == 0 and "\tpath\tvaultquorum" in metadata.stdout


def commitment(case_id: str, epoch: str, secret: int) -> str:
    """Compute the documented commitment for one epoch secret."""
    payload = f"{case_id}\n{epoch}\n{secret}\n".encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def transition_seal(
    case_id: str,
    parent: str,
    child: str,
    offset: int,
    parent_secret: int,
    child_secret: int,
    holders: list[str],
) -> str:
    """Bind one refresh edge to the exact model secrets and continuity witness."""
    payload = (
        f"{case_id}\n{parent}\n{child}\n{offset}\n{parent_secret}\n"
        f"{child_secret}\n{','.join(holders)}\n"
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def lineage_edge(
    case_id: str,
    parent: str,
    child: str,
    offset: int,
    parent_secret: int,
    child_secret: int,
    holders: list[str],
    *,
    alternate_holders: list[list[str]] | None = None,
    continuity_roles: list[str] | None = None,
    continuity_quorum: int = 3,
) -> dict:
    """Build a refresh edge with one or more model-bound handoff authorizations."""
    roles = (
        continuity_roles if continuity_roles is not None else ["ops", "legal", "sre"]
    )
    return {
        "parent": parent,
        "child": child,
        "offset": offset,
        "continuity_roles": roles,
        "continuity_quorum": continuity_quorum,
        "handoff_seals": [
            transition_seal(
                case_id,
                parent,
                child,
                offset,
                parent_secret,
                child_secret,
                authorized,
            )
            for authorized in [holders, *(alternate_holders or [])]
        ],
    }


def sign(case_id: str, key: bytes, share: dict) -> str:
    """Authenticate one share with the specified line-oriented HMAC payload."""
    message = "{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n".format(
        case_id,
        share["holder"],
        share["role"],
        share["epoch"],
        share["x"],
        share["y"],
        share["not_before"],
        share["not_after"],
        share["state"],
    ).encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def make_share(
    case_id: str,
    key: bytes,
    holder: str,
    role: str,
    epoch: str,
    x: int,
    y: int,
    *,
    state: str = "active",
    not_before: int = 10,
    not_after: int = 80,
) -> dict:
    """Build and authenticate one verifier share."""
    share = {
        "holder": holder,
        "role": role,
        "epoch": epoch,
        "x": x,
        "y": y,
        "state": state,
        "not_before": not_before,
        "not_after": not_after,
    }
    share["mac"] = sign(case_id, key, share)
    return share


def y_at(secret: int, coeffs: list[int], x: int, prime: int = PRIME) -> int:
    """Evaluate a coefficient-form polynomial modulo prime."""
    total = secret
    power = x
    for coeff in coeffs:
        total = (total + coeff * power) % prime
        power = (power * x) % prime
    return total


def polynomial_shares(
    case_id: str,
    key: bytes,
    epoch: str,
    secret: int,
    coeffs: list[int],
    holders: list[tuple[str, str, int]],
    *,
    prime: int = PRIME,
) -> list[dict]:
    """Create signed shares lying on one polynomial."""
    return [
        make_share(case_id, key, holder, role, epoch, x, y_at(secret, coeffs, x, prime))
        for holder, role, x in holders
    ]


def make_case(
    case_id: str,
    key: bytes,
    shares: list[dict],
    commitments: dict[str, str],
    *,
    threshold: int = 3,
    max_outliers: int = 0,
    required_roles: list[str] | None = None,
    role_limits: dict[str, int] | None = None,
    lineage: list[dict] | None = None,
    min_lineage_depth: int = 1,
    prime: int = PRIME,
) -> dict:
    """Assemble a valid checker input with convenient policy defaults."""
    return {
        "case_id": case_id,
        "prime": prime,
        "threshold": threshold,
        "max_outliers": max_outliers,
        "audit_time": 40,
        "auth_key_hex": key.hex(),
        "required_roles": required_roles
        if required_roles is not None
        else ["ops", "legal", "sre"],
        "role_limits": role_limits
        if role_limits is not None
        else {"ops": 1, "legal": 1, "sre": 1},
        "commitments": commitments,
        "lineage": lineage if lineage is not None else [],
        "min_lineage_depth": min_lineage_depth,
        "shares": shares,
    }


def interpolate(points: tuple[dict, ...] | list[dict], x: int, prime: int) -> int:
    """Evaluate the unique low-degree polynomial through points at x modulo prime."""
    total = 0
    for index, point in enumerate(points):
        numerator = 1
        denominator = 1
        for other_index, other in enumerate(points):
            if index == other_index:
                continue
            numerator = (numerator * (x - other["x"])) % prime
            denominator = (denominator * (point["x"] - other["x"])) % prime
        total = (total + point["y"] * numerator * pow(denominator, -1, prime)) % prime
    return total


def best_witness(case: dict, support: list[dict]) -> list[str]:
    """Return the lexicographically first threshold witness satisfying the policy."""
    ordered = sorted(support, key=lambda share: (share["holder"], share["x"]))
    valid: list[list[str]] = []
    for subset in combinations(ordered, case["threshold"]):
        counts: dict[str, int] = {}
        for share in subset:
            counts[share["role"]] = counts.get(share["role"], 0) + 1
        if any(counts.get(role, 0) == 0 for role in case["required_roles"]):
            continue
        if any(counts.get(role, 0) > cap for role, cap in case["role_limits"].items()):
            continue
        valid.append(sorted(share["holder"] for share in subset))
    return min(valid) if valid else []


def continuity_witnesses(
    parent_support: list[dict],
    child_support: list[dict],
    edge: dict,
    used_holders: set[str] | frozenset[str] | None = None,
) -> list[list[str]]:
    """Enumerate role-stable quorums after excluding holders used earlier in the path."""
    used = set() if used_holders is None else set(used_holders)
    child_by_holder = {share["holder"]: share for share in child_support}
    candidates = sorted(
        (
            share
            for share in parent_support
            if share["holder"] not in used
            and share["holder"] in child_by_holder
            and child_by_holder[share["holder"]]["role"] == share["role"]
        ),
        key=lambda share: share["holder"],
    )
    valid: list[list[str]] = []
    for subset in combinations(candidates, edge["continuity_quorum"]):
        roles = {share["role"] for share in subset}
        if all(role in roles for role in edge["continuity_roles"]):
            valid.append(sorted(share["holder"] for share in subset))
    return sorted(valid)


def expected_model_frontier(case: dict) -> tuple[int, str, list[bytes]]:
    """Independently enumerate models, path states, and canonical frontier records."""
    key = bytes.fromhex(case["auth_key_hex"])
    initial = [
        share
        for share in case["shares"]
        if hmac.compare_digest(sign(case["case_id"], key, share), share["mac"])
        and share["state"] == "active"
        and share["not_before"] <= case["audit_time"] <= share["not_after"]
    ]
    coordinate_counts: dict[tuple[str, int], int] = {}
    for share in initial:
        coordinate = (share["epoch"], share["x"])
        coordinate_counts[coordinate] = coordinate_counts.get(coordinate, 0) + 1
    eligible = [
        share
        for share in initial
        if coordinate_counts[(share["epoch"], share["x"])] == 1
    ]

    models: list[dict] = []
    for epoch in sorted({share["epoch"] for share in eligible}):
        epoch_shares = sorted(
            (share for share in eligible if share["epoch"] == epoch),
            key=lambda share: (share["holder"], share["x"]),
        )
        if len(epoch_shares) < case["threshold"]:
            continue
        seen_models: set[tuple[int, ...]] = set()
        for seed in combinations(epoch_shares, case["threshold"]):
            identity = tuple(
                interpolate(seed, x, case["prime"]) for x in range(case["threshold"])
            )
            if identity in seen_models:
                continue
            seen_models.add(identity)
            support = [
                share
                for share in epoch_shares
                if interpolate(seed, share["x"], case["prime"]) == share["y"]
            ]
            outliers = [share for share in epoch_shares if share not in support]
            if len(outliers) > case["max_outliers"]:
                continue
            witness = best_witness(case, support)
            secret = interpolate(seed, 0, case["prime"])
            commitment_ok = (
                commitment(case["case_id"], epoch, secret) == case["commitments"][epoch]
            )
            models.append(
                {
                    "epoch": epoch,
                    "support": support,
                    "outliers": outliers,
                    "witness": witness,
                    "secret": secret,
                    "policy_ok": bool(witness),
                    "commitment_ok": commitment_ok,
                    "lineage_depth": 0,
                    "lineage_epochs": [],
                    "continuity_holders": [],
                    "continuity_chain": [],
                    "states": {},
                }
            )

    incoming: dict[str, list[dict]] = {}
    outgoing: dict[str, list[str]] = {}
    indegree = {epoch: 0 for epoch in case["commitments"]}
    for edge in case["lineage"]:
        incoming.setdefault(edge["child"], []).append(edge)
        outgoing.setdefault(edge["parent"], []).append(edge["child"])
        indegree[edge["child"]] += 1
    for edges in incoming.values():
        edges.sort(key=lambda edge: (edge["parent"], edge["child"]))

    queue = sorted(epoch for epoch, degree in indegree.items() if degree == 0)
    topological: list[str] = []
    while queue:
        epoch = queue.pop(0)
        topological.append(epoch)
        for child in sorted(outgoing.get(epoch, [])):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()

    models_by_epoch: dict[str, list[dict]] = {}
    for model in models:
        models_by_epoch.setdefault(model["epoch"], []).append(model)

    def state_key(state: dict) -> tuple:
        return (
            -state["depth"],
            tuple(state["epochs"]),
            tuple(tuple(holders) for holders in state["chain"]),
        )

    for epoch in topological:
        for model in models_by_epoch.get(epoch, []):
            if not model["policy_ok"] or not model["commitment_ok"]:
                continue
            if epoch not in incoming:
                model["states"][frozenset()] = {
                    "depth": 1,
                    "epochs": [epoch],
                    "chain": [],
                    "used": frozenset(),
                }
            for edge in incoming.get(epoch, []):
                for parent in models_by_epoch.get(edge["parent"], []):
                    if (
                        model["secret"]
                        != (parent["secret"] + edge["offset"]) % case["prime"]
                    ):
                        continue
                    for parent_state in parent["states"].values():
                        for holders in continuity_witnesses(
                            parent["support"],
                            model["support"],
                            edge,
                            parent_state["used"],
                        ):
                            expected_seal = transition_seal(
                                case["case_id"],
                                edge["parent"],
                                edge["child"],
                                edge["offset"],
                                parent["secret"],
                                model["secret"],
                                holders,
                            )
                            if expected_seal not in edge["handoff_seals"]:
                                continue
                            used = frozenset(set(parent_state["used"]) | set(holders))
                            state = {
                                "depth": parent_state["depth"] + 1,
                                "epochs": [*parent_state["epochs"], epoch],
                                "chain": [*parent_state["chain"], holders],
                                "used": used,
                            }
                            current = model["states"].get(used)
                            if current is None or state_key(state) < state_key(current):
                                model["states"][used] = state
            if model["states"]:
                best = min(model["states"].values(), key=state_key)
                model["lineage_depth"] = best["depth"]
                model["lineage_epochs"] = best["epochs"]
                model["continuity_chain"] = best["chain"]
                model["continuity_holders"] = best["chain"][-1] if best["chain"] else []

    def encode(value: str) -> str:
        return value.encode().hex()

    records: list[bytes] = []
    for model in models:
        chain = ";".join(
            ",".join(encode(holder) for holder in holders)
            for holders in model["continuity_chain"]
        )
        record = "|".join(
            [
                encode(model["epoch"]),
                str(model["secret"]),
                ",".join(
                    encode(share["holder"])
                    for share in sorted(
                        model["support"], key=lambda item: item["holder"]
                    )
                ),
                ",".join(
                    encode(share["holder"])
                    for share in sorted(
                        model["outliers"], key=lambda item: item["holder"]
                    )
                ),
                ",".join(encode(holder) for holder in model["witness"]),
                "1" if model["policy_ok"] else "0",
                "1" if model["commitment_ok"] else "0",
                str(model["lineage_depth"]),
                ",".join(encode(holder) for holder in model["continuity_holders"]),
                ",".join(encode(epoch) for epoch in model["lineage_epochs"]),
                chain,
            ]
        ).encode()
        records.append(record)

    records.sort()
    payload = b"".join(record + b"\n" for record in records)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return len(records), digest, records


def evidence_digest(report: dict) -> str:
    """Recompute the final evidence digest from the exact output fields."""
    reason = report["reason"] or ""
    epoch = report["selected_epoch"] or ""
    secret = report["secret_mod"] or ""
    rejected = ",".join(
        f"{item['epoch']}/{item['holder']}:{item['reason']}"
        for item in report["rejected"]
    )
    payload = (
        f"{report['case_id']}\n{report['status']}\n{reason}\n{epoch}\n"
        f"{','.join(report['lineage_epochs'])}\n"
        f"{','.join(report['continuity_holders'])}\n"
        f"{';'.join(','.join(holders) for holders in report['continuity_chain'])}\n"
        f"{','.join(report['selected_holders'])}\n{','.join(report['support_holders'])}\n"
        f"{','.join(report['outlier_holders'])}\n{report['support_share_count']}\n"
        f"{secret}\n{report['valid_share_count']}\n{report['evaluated_model_count']}\n"
        f"{report['model_frontier_digest']}\n{rejected}\n"
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def child_env() -> dict[str, str]:
    """Return the restricted runtime environment used for product executions."""
    env = os.environ.copy()
    env["PATH"] = "/app/bin"
    return env


def run_case(
    tmp_path: Path, case: dict
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Write one input, execute the rebuilt binary, and return its output path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "case.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(case, separators=(",", ":")), encoding="utf-8")
    result = subprocess.run(
        [str(BIN), str(input_path), str(output_path)],
        cwd=APP,
        env=child_env(),
        text=True,
        capture_output=True,
        timeout=20,
    )
    return result, output_path


def load_success(tmp_path: Path, case: dict) -> tuple[dict, bytes]:
    """Run a valid case and verify common output, schema, and frontier properties."""
    result, output_path = run_case(tmp_path, case)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    raw = output_path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    report = json.loads(raw)
    assert_report_shape(report)
    expected_count, expected_digest, _ = expected_model_frontier(case)
    assert report["evaluated_model_count"] == expected_count
    assert report["model_frontier_digest"] == expected_digest
    return report, raw


def assert_report_shape(report: dict) -> None:
    """Check exact report keys, types, enums, ordering, nulls, and digests."""
    assert set(report) == {
        "case_id",
        "status",
        "reason",
        "selected_epoch",
        "lineage_epochs",
        "continuity_holders",
        "continuity_chain",
        "selected_holders",
        "support_holders",
        "outlier_holders",
        "support_share_count",
        "secret_mod",
        "valid_share_count",
        "evaluated_model_count",
        "model_frontier_digest",
        "rejected",
        "evidence_digest",
    }
    assert isinstance(report["case_id"], str)
    assert report["status"] in {"recovered", "blocked"}
    assert report["reason"] is None or report["reason"] in {
        "not_enough_valid_shares",
        "consensus_not_reached",
        "role_requirement_unsatisfied",
        "commitment_mismatch",
        "lineage_not_reached",
    }
    assert report["selected_epoch"] is None or isinstance(report["selected_epoch"], str)
    for field in (
        "lineage_epochs",
        "continuity_holders",
        "selected_holders",
        "support_holders",
        "outlier_holders",
    ):
        assert isinstance(report[field], list)
        assert all(isinstance(value, str) and value for value in report[field])
    for field in (
        "continuity_holders",
        "selected_holders",
        "support_holders",
        "outlier_holders",
    ):
        assert report[field] == sorted(report[field])
    assert isinstance(report["continuity_chain"], list)
    assert all(isinstance(edge, list) and edge for edge in report["continuity_chain"])
    assert all(
        all(isinstance(holder, str) and holder for holder in edge)
        for edge in report["continuity_chain"]
    )
    assert all(edge == sorted(edge) for edge in report["continuity_chain"])
    flattened_continuity = [
        holder for edge in report["continuity_chain"] for holder in edge
    ]
    assert len(flattened_continuity) == len(set(flattened_continuity))
    assert (
        type(report["support_share_count"]) is int
        and report["support_share_count"] >= 0
    )
    assert report["support_share_count"] == len(report["support_holders"])
    assert report["secret_mod"] is None or (
        isinstance(report["secret_mod"], str)
        and re.fullmatch(r"0|[1-9][0-9]*", report["secret_mod"])
    )
    assert type(report["valid_share_count"]) is int and report["valid_share_count"] >= 0
    assert (
        type(report["evaluated_model_count"]) is int
        and report["evaluated_model_count"] >= 0
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", report["model_frontier_digest"])
    assert isinstance(report["rejected"], list)
    assert report["rejected"] == sorted(
        report["rejected"],
        key=lambda item: (item["epoch"], item["holder"], item["reason"]),
    )
    assert all(
        set(item) == {"epoch", "holder", "reason"} for item in report["rejected"]
    )
    assert all(
        item["reason"] in {"bad_mac", "inactive", "outside_window", "duplicate_x"}
        for item in report["rejected"]
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", report["evidence_digest"])
    assert report["evidence_digest"] == evidence_digest(report)
    if report["status"] == "recovered":
        assert report["reason"] is None
        assert isinstance(report["selected_epoch"], str)
        assert report["lineage_epochs"]
        assert report["lineage_epochs"][-1] == report["selected_epoch"]
        assert len(report["continuity_chain"]) == len(report["lineage_epochs"]) - 1
        assert report["continuity_holders"] == (
            report["continuity_chain"][-1] if report["continuity_chain"] else []
        )
        assert report["selected_holders"]
        assert report["support_holders"]
        assert set(report["selected_holders"]).issubset(report["support_holders"])
        assert not set(report["support_holders"]) & set(report["outlier_holders"])
        assert isinstance(report["secret_mod"], str)
    else:
        assert report["reason"] is not None
        assert report["selected_epoch"] is None
        assert report["lineage_epochs"] == []
        assert report["continuity_holders"] == []
        assert report["continuity_chain"] == []
        assert report["selected_holders"] == []
        assert report["support_holders"] == []
        assert report["outlier_holders"] == []
        assert report["support_share_count"] == 0
        assert report["secret_mod"] is None


def test_robust_model_recovers_with_authenticated_outliers(tmp_path: Path) -> None:
    """Recovery must couple polynomial support, outlier budget, policy witness, commitment, and digest."""
    case_id = "robust-recovery"
    epoch = "epoch-r"
    key = b"robust-recovery-key"
    secret = 173
    good = polynomial_shares(
        case_id,
        key,
        epoch,
        secret,
        [19, 7],
        [("aa", "ops", 1), ("ba", "legal", 2), ("ca", "sre", 3), ("da", "ops", 4)],
    )
    outliers = [
        make_share(
            case_id, key, "ea", "ops", epoch, 5, (y_at(secret, [19, 7], 5) + 31) % PRIME
        ),
        make_share(
            case_id,
            key,
            "fa",
            "legal",
            epoch,
            6,
            (y_at(secret, [19, 7], 6) + 47) % PRIME,
        ),
    ]
    case = make_case(
        case_id,
        key,
        [*good, *outliers],
        {epoch: commitment(case_id, epoch, secret)},
        max_outliers=2,
    )

    report, _ = load_success(tmp_path, case)
    assert report["status"] == "recovered"
    assert report["selected_epoch"] == epoch
    assert report["selected_holders"] == ["aa", "ba", "ca"]
    assert report["support_holders"] == ["aa", "ba", "ca", "da"]
    assert report["outlier_holders"] == ["ea", "fa"]
    assert report["support_share_count"] == 4
    assert report["valid_share_count"] == 6
    assert report["secret_mod"] == str(secret)


def test_larger_support_beats_lexicographically_earlier_epoch(tmp_path: Path) -> None:
    """Selection must prioritize the strongest supported model before applying epoch ordering."""
    case_id = "support-before-epoch"
    key = b"support-before-epoch-key"
    alpha_secret = 51
    beta_secret = 199
    alpha = polynomial_shares(
        case_id,
        key,
        "alpha",
        alpha_secret,
        [4, 9],
        [("a-ops", "ops", 1), ("a-legal", "legal", 2), ("a-sre", "sre", 3)],
    )
    alpha.append(make_share(case_id, key, "a-noise", "ops", "alpha", 4, 88))
    beta = polynomial_shares(
        case_id,
        key,
        "beta",
        beta_secret,
        [12, 5],
        [
            ("z-ops", "ops", 1),
            ("z-legal", "legal", 2),
            ("z-sre", "sre", 3),
            ("z-extra", "ops", 4),
        ],
    )
    case = make_case(
        case_id,
        key,
        [*alpha, *beta],
        {
            "alpha": commitment(case_id, "alpha", alpha_secret),
            "beta": commitment(case_id, "beta", beta_secret),
        },
        max_outliers=1,
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "beta"
    assert report["support_share_count"] == 4
    assert report["support_holders"] == ["z-extra", "z-legal", "z-ops", "z-sre"]
    assert report["outlier_holders"] == []
    assert report["secret_mod"] == str(beta_secret)


def test_equal_support_uses_epoch_tiebreak(tmp_path: Path) -> None:
    """Equal support across epochs must use the documented epoch ordering, not map order."""
    case_id = "epoch-tiebreak"
    key = b"epoch-tiebreak-key"
    holders = [("ops-one", "ops", 1), ("legal-one", "legal", 2), ("sre-one", "sre", 3)]
    alpha_secret = 87
    beta_secret = 143
    alpha = polynomial_shares(case_id, key, "alpha", alpha_secret, [6, 2], holders)
    beta = polynomial_shares(case_id, key, "beta", beta_secret, [8, 11], holders)
    case = make_case(
        case_id,
        key,
        [*beta, *alpha],
        {
            "alpha": commitment(case_id, "alpha", alpha_secret),
            "beta": commitment(case_id, "beta", beta_secret),
        },
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "alpha"
    assert report["selected_holders"] == ["legal-one", "ops-one", "sre-one"]
    assert report["secret_mod"] == str(alpha_secret)


def test_same_epoch_equal_support_uses_witness_holder_tiebreak(tmp_path: Path) -> None:
    """Two accepted models in one epoch must select the lexicographically smaller witness list."""
    case_id = "same-epoch-witness-tiebreak"
    epoch = "rotation"
    key = b"same-epoch-witness-key"
    secret = 77
    later_witness = polynomial_shares(
        case_id,
        key,
        epoch,
        secret,
        [11],
        [("b-legal", "legal", 3), ("c-ops", "ops", 4)],
    )
    earlier_witness = polynomial_shares(
        case_id,
        key,
        epoch,
        secret,
        [5],
        [("a-legal", "legal", 1), ("z-ops", "ops", 2)],
    )
    case = make_case(
        case_id,
        key,
        [*later_witness, *earlier_witness],
        {epoch: commitment(case_id, epoch, secret)},
        threshold=2,
        max_outliers=2,
        required_roles=["ops", "legal"],
        role_limits={"ops": 1, "legal": 1},
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == epoch
    assert report["selected_holders"] == ["a-legal", "z-ops"]
    assert report["support_holders"] == ["a-legal", "z-ops"]
    assert report["support_share_count"] == 2
    assert report["secret_mod"] == str(secret)


def test_nonwinning_consensus_model_changes_frontier_not_winner(tmp_path: Path) -> None:
    """A commitment-failing consensus model must alter the frontier audit without changing recovery."""
    case_id = "frontier-nonwinner"
    key = b"frontier-nonwinner-key"
    primary_secret = 41
    secondary_secret = 193
    primary = polynomial_shares(
        case_id,
        key,
        "alpha",
        primary_secret,
        [7, 3],
        [("a1", "ops", 1), ("a2", "legal", 2), ("a3", "sre", 3), ("a4", "ops", 4)],
    )
    secondary_good = polynomial_shares(
        case_id,
        key,
        "omega",
        secondary_secret,
        [9, 5],
        [("o1", "ops", 5), ("o2", "legal", 6), ("o3", "sre", 7), ("o4", "ops", 8)],
    )
    secondary_broken = copy.deepcopy(secondary_good)
    secondary_broken[-1]["y"] = (secondary_broken[-1]["y"] + 1) % PRIME
    secondary_broken[-1]["mac"] = sign(case_id, key, secondary_broken[-1])
    commitments = {
        "alpha": commitment(case_id, "alpha", primary_secret),
        "omega": commitment(case_id, "omega", secondary_secret + 1),
    }
    without_secondary_consensus = make_case(
        case_id,
        key,
        [*primary, *secondary_broken],
        commitments,
    )
    with_secondary_consensus = make_case(
        case_id,
        key,
        [*primary, *secondary_good],
        commitments,
    )

    first, _ = load_success(tmp_path / "broken", without_secondary_consensus)
    second, _ = load_success(tmp_path / "consensus", with_secondary_consensus)
    for report in (first, second):
        assert report["selected_epoch"] == "alpha"
        assert report["support_holders"] == ["a1", "a2", "a3", "a4"]
        assert report["secret_mod"] == str(primary_secret)
        assert report["valid_share_count"] == 8
    assert second["evaluated_model_count"] == first["evaluated_model_count"] + 1
    assert first["model_frontier_digest"] != second["model_frontier_digest"]
    assert first["evidence_digest"] != second["evidence_digest"]


def test_frontier_deduplicates_threshold_subsets_of_one_polynomial(
    tmp_path: Path,
) -> None:
    """Many threshold subsets of the same polynomial must contribute one frontier model."""
    case_id = "frontier-dedup"
    epoch = "stable"
    key = b"frontier-dedup-key"
    secret = 129
    shares = polynomial_shares(
        case_id,
        key,
        epoch,
        secret,
        [15, 4],
        [
            ("d1", "ops", 1),
            ("d2", "legal", 2),
            ("d3", "sre", 3),
            ("d4", "ops", 4),
            ("d5", "legal", 5),
        ],
    )
    case = make_case(case_id, key, shares, {epoch: commitment(case_id, epoch, secret)})

    report, _ = load_success(tmp_path, case)
    assert report["status"] == "recovered"
    assert report["support_share_count"] == 5
    assert report["evaluated_model_count"] == 1


def test_commitment_search_skips_first_consensus_model(tmp_path: Path) -> None:
    """A commitment mismatch on one robust model must not prevent a later model from recovering."""
    case_id = "commitment-model-search"
    epoch = "rotation-9"
    key = b"commitment-model-key"
    wrong_secret = 31
    right_secret = 211
    wrong = polynomial_shares(
        case_id,
        key,
        epoch,
        wrong_secret,
        [3, 17],
        [("aa", "ops", 1), ("ba", "legal", 2), ("ca", "sre", 3)],
    )
    right = polynomial_shares(
        case_id,
        key,
        epoch,
        right_secret,
        [21, 4],
        [("da", "ops", 4), ("ea", "legal", 5), ("fa", "sre", 6)],
    )
    case = make_case(
        case_id,
        key,
        [*wrong, *right],
        {epoch: commitment(case_id, epoch, right_secret)},
        max_outliers=3,
    )

    report, _ = load_success(tmp_path, case)
    assert report["status"] == "recovered"
    assert report["selected_holders"] == ["da", "ea", "fa"]
    assert report["support_holders"] == ["da", "ea", "fa"]
    assert report["outlier_holders"] == ["aa", "ba", "ca"]
    assert report["secret_mod"] == str(right_secret)


def test_policy_is_evaluated_inside_each_consensus_support_set(tmp_path: Path) -> None:
    """A larger consensus model without a legal witness cannot outrank a smaller policy-compliant model."""
    case_id = "policy-inside-support"
    key = b"policy-inside-support-key"
    alpha_secret = 61
    beta_secret = 111
    alpha = polynomial_shares(
        case_id,
        key,
        "alpha",
        alpha_secret,
        [5, 3],
        [
            ("a1", "ops", 1),
            ("a2", "ops", 2),
            ("a3", "ops", 3),
            ("a4", "legal", 4),
            ("a5", "legal", 5),
        ],
    )
    beta = polynomial_shares(
        case_id,
        key,
        "beta",
        beta_secret,
        [7, 13],
        [("b1", "ops", 1), ("b2", "legal", 2), ("b3", "sre", 3), ("b4", "ops", 4)],
    )
    case = make_case(
        case_id,
        key,
        [*alpha, *beta],
        {
            "alpha": commitment(case_id, "alpha", alpha_secret),
            "beta": commitment(case_id, "beta", beta_secret),
        },
        required_roles=["ops", "legal", "sre"],
        role_limits={"ops": 1, "legal": 1, "sre": 1},
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "beta"
    assert report["selected_holders"] == ["b1", "b2", "b3"]
    assert report["support_share_count"] == 4


def test_authentication_precedence_and_epoch_local_duplicates(tmp_path: Path) -> None:
    """MAC, activity, time, and duplicate-coordinate rejections must keep their precedence and epoch scope."""
    case_id = "rejection-pipeline"
    key = b"rejection-pipeline-key"
    good_secret = 101
    good = polynomial_shares(
        case_id,
        key,
        "good",
        good_secret,
        [8, 6],
        [("g-ops", "ops", 1), ("g-legal", "legal", 2), ("g-sre", "sre", 3)],
    )
    bad_mac = make_share(
        case_id, key, "bad", "ops", "bad-epoch", 1, 10, state="revoked", not_after=20
    )
    bad_mac["mac"] = "0" * 64
    inactive = make_share(
        case_id,
        key,
        "inactive",
        "legal",
        "bad-epoch",
        2,
        20,
        state="revoked",
        not_after=20,
    )
    outside = make_share(
        case_id, key, "outside", "sre", "bad-epoch", 3, 30, not_after=20
    )
    duplicate_a = make_share(case_id, key, "dup-a", "ops", "dup-epoch", 7, 40)
    duplicate_b = make_share(case_id, key, "dup-b", "legal", "dup-epoch", 7, 50)
    case = make_case(
        case_id,
        key,
        [bad_mac, inactive, outside, duplicate_a, duplicate_b, *good],
        {
            "bad-epoch": commitment(case_id, "bad-epoch", 1),
            "dup-epoch": commitment(case_id, "dup-epoch", 2),
            "good": commitment(case_id, "good", good_secret),
        },
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "good"
    assert report["valid_share_count"] == 3
    assert report["rejected"] == [
        {"epoch": "bad-epoch", "holder": "bad", "reason": "bad_mac"},
        {"epoch": "bad-epoch", "holder": "inactive", "reason": "inactive"},
        {"epoch": "bad-epoch", "holder": "outside", "reason": "outside_window"},
        {"epoch": "dup-epoch", "holder": "dup-a", "reason": "duplicate_x"},
        {"epoch": "dup-epoch", "holder": "dup-b", "reason": "duplicate_x"},
    ]


def test_deeper_lineage_beats_a_stronger_standalone_epoch(tmp_path: Path) -> None:
    """A verified refresh chain must outrank a larger committed model that has no parent history."""
    case_id = "lineage-before-support"
    key = b"lineage-before-support-key"
    root_secret = 47
    child_secret = 56
    standalone_secret = 201
    root = polynomial_shares(
        case_id,
        key,
        "root",
        root_secret,
        [5, 2],
        [("r-ops", "ops", 1), ("r-legal", "legal", 2), ("r-sre", "sre", 3)],
    )
    child = polynomial_shares(
        case_id,
        key,
        "child",
        child_secret,
        [7, 4],
        [("r-ops", "ops", 1), ("r-legal", "legal", 2), ("r-sre", "sre", 3)],
    )
    standalone = polynomial_shares(
        case_id,
        key,
        "standalone",
        standalone_secret,
        [11, 3],
        [
            ("s-ops", "ops", 1),
            ("s-legal", "legal", 2),
            ("s-sre", "sre", 3),
            ("s-extra-a", "ops", 4),
            ("s-extra-b", "legal", 5),
        ],
    )
    case = make_case(
        case_id,
        key,
        [*standalone, *child, *root],
        {
            "root": commitment(case_id, "root", root_secret),
            "child": commitment(case_id, "child", child_secret),
            "standalone": commitment(case_id, "standalone", standalone_secret),
        },
        lineage=[
            lineage_edge(
                case_id,
                "root",
                "child",
                9,
                root_secret,
                child_secret,
                ["r-legal", "r-ops", "r-sre"],
            )
        ],
    )

    report, _ = load_success(tmp_path, case)
    assert report["status"] == "recovered"
    assert report["selected_epoch"] == "child"
    assert report["lineage_epochs"] == ["root", "child"]
    assert report["support_share_count"] == 3
    assert report["secret_mod"] == str(child_secret)


def test_lineage_search_skips_an_incompatible_first_parent_model(
    tmp_path: Path,
) -> None:
    """Child linkage must search every parent consensus model rather than only the first polynomial found."""
    case_id = "lineage-parent-search"
    key = b"lineage-parent-search-key"
    wrong_parent_secret = 33
    right_parent_secret = 141
    child_secret = 158
    wrong_parent = polynomial_shares(
        case_id,
        key,
        "parent",
        wrong_parent_secret,
        [3, 5],
        [("aa", "ops", 1), ("ba", "legal", 2), ("ca", "sre", 3)],
    )
    right_parent = polynomial_shares(
        case_id,
        key,
        "parent",
        right_parent_secret,
        [9, 7],
        [("da", "ops", 4), ("ea", "legal", 5), ("fa", "sre", 6)],
    )
    child = polynomial_shares(
        case_id,
        key,
        "child",
        child_secret,
        [13, 2],
        [("da", "ops", 1), ("ea", "legal", 2), ("fa", "sre", 3)],
    )
    case = make_case(
        case_id,
        key,
        [*wrong_parent, *right_parent, *child],
        {
            "parent": commitment(case_id, "parent", right_parent_secret),
            "child": commitment(case_id, "child", child_secret),
        },
        max_outliers=3,
        lineage=[
            lineage_edge(
                case_id,
                "parent",
                "child",
                17,
                right_parent_secret,
                child_secret,
                ["da", "ea", "fa"],
            )
        ],
        min_lineage_depth=2,
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "child"
    assert report["lineage_epochs"] == ["parent", "child"]
    assert report["secret_mod"] == str(child_secret)
    assert report["evaluated_model_count"] >= 3


def test_nonpreferred_parent_state_enables_deeper_disjoint_lineage(
    tmp_path: Path,
) -> None:
    """Lineage search must retain a nonpreferred path when its unused holders enable a deeper sealed edge."""
    case_id = "disjoint-lineage-state"
    key = b"disjoint-lineage-state-key"
    secrets = {"a-root": 21, "b-root": 57, "mid": 91, "leaf": 132}
    group_a = [("a", "ops", 1), ("b", "legal", 2), ("c", "sre", 3)]
    group_b = [("d", "ops", 1), ("e", "legal", 2), ("f", "sre", 3)]
    both_groups = [
        ("a", "ops", 1),
        ("b", "legal", 2),
        ("c", "sre", 3),
        ("d", "ops", 4),
        ("e", "legal", 5),
        ("f", "sre", 6),
    ]
    shares = [
        *polynomial_shares(case_id, key, "a-root", secrets["a-root"], [5, 2], group_a),
        *polynomial_shares(case_id, key, "b-root", secrets["b-root"], [7, 3], group_b),
        *polynomial_shares(case_id, key, "mid", secrets["mid"], [11, 4], both_groups),
        *polynomial_shares(case_id, key, "leaf", secrets["leaf"], [13, 6], both_groups),
    ]
    lineage = [
        lineage_edge(
            case_id,
            "a-root",
            "mid",
            secrets["mid"] - secrets["a-root"],
            secrets["a-root"],
            secrets["mid"],
            ["a", "b", "c"],
        ),
        lineage_edge(
            case_id,
            "b-root",
            "mid",
            secrets["mid"] - secrets["b-root"],
            secrets["b-root"],
            secrets["mid"],
            ["d", "e", "f"],
        ),
        lineage_edge(
            case_id,
            "mid",
            "leaf",
            secrets["leaf"] - secrets["mid"],
            secrets["mid"],
            secrets["leaf"],
            ["a", "b", "c"],
        ),
    ]
    case = make_case(
        case_id,
        key,
        shares,
        {
            epoch: commitment(case_id, epoch, secret)
            for epoch, secret in secrets.items()
        },
        lineage=lineage,
        min_lineage_depth=3,
    )

    report, _ = load_success(tmp_path, case)
    assert report["selected_epoch"] == "leaf"
    assert report["lineage_epochs"] == ["b-root", "mid", "leaf"]
    assert report["continuity_chain"] == [["d", "e", "f"], ["a", "b", "c"]]
    assert report["continuity_holders"] == ["a", "b", "c"]
    assert len({holder for edge in report["continuity_chain"] for holder in edge}) == 6


def test_dynamic_disjoint_dag_variants_defeat_greedy_lineage(tmp_path: Path) -> None:
    """Two fresh DAGs must keep alternate path states instead of emitting a locally greedy lineage report."""
    seed = hashlib.sha256(str(tmp_path).encode()).digest()

    def build_variant(label: str) -> tuple[dict, list[str], list[list[str]], str]:
        token = hashlib.sha256(seed + label.encode()).hexdigest()[:8]
        case_id = f"dag-{label}-{token}"
        key = hashlib.sha256(seed + b"dag-key-" + label.encode()).digest()[:16]
        epochs = {
            "a": f"a-root-{token}",
            "b": f"b-root-{token}",
            "mid": f"mid-{token}",
            "leaf": f"leaf-{token}",
        }
        root_a = 10 + seed[0] % 40
        root_b = 60 + seed[1] % 40
        mid = (root_b + 17 + seed[2] % 20) % PRIME
        leaf = (mid + 23 + seed[3] % 20) % PRIME
        secrets = {
            epochs["a"]: root_a,
            epochs["b"]: root_b,
            epochs["mid"]: mid,
            epochs["leaf"]: leaf,
        }
        group_a = [
            (f"{label}-{token}-a1", "ops", 1),
            (f"{label}-{token}-a2", "legal", 2),
            (f"{label}-{token}-a3", "sre", 3),
        ]
        group_b = [
            (f"{label}-{token}-b1", "ops", 1),
            (f"{label}-{token}-b2", "legal", 2),
            (f"{label}-{token}-b3", "sre", 3),
        ]
        combined = [*group_a, *[(holder, role, x + 3) for holder, role, x in group_b]]
        shares = [
            *polynomial_shares(case_id, key, epochs["a"], root_a, [3, 5], group_a),
            *polynomial_shares(case_id, key, epochs["b"], root_b, [7, 9], group_b),
            *polynomial_shares(case_id, key, epochs["mid"], mid, [11, 13], combined),
            *polynomial_shares(case_id, key, epochs["leaf"], leaf, [17, 19], combined),
        ]
        holders_a = sorted(holder for holder, _, _ in group_a)
        holders_b = sorted(holder for holder, _, _ in group_b)
        lineage = [
            lineage_edge(
                case_id,
                epochs["a"],
                epochs["mid"],
                (mid - root_a) % PRIME,
                root_a,
                mid,
                holders_a,
            ),
            lineage_edge(
                case_id,
                epochs["b"],
                epochs["mid"],
                (mid - root_b) % PRIME,
                root_b,
                mid,
                holders_b,
            ),
            lineage_edge(
                case_id,
                epochs["mid"],
                epochs["leaf"],
                (leaf - mid) % PRIME,
                mid,
                leaf,
                holders_a,
            ),
        ]
        case = make_case(
            case_id,
            key,
            shares,
            {
                epoch: commitment(case_id, epoch, secret)
                for epoch, secret in secrets.items()
            },
            lineage=lineage,
            min_lineage_depth=3,
        )
        return (
            case,
            [epochs["b"], epochs["mid"], epochs["leaf"]],
            [holders_b, holders_a],
            str(leaf),
        )

    first_case, first_path, first_chain, first_secret = build_variant("one")
    second_case, second_path, second_chain, second_secret = build_variant("two")
    first, _ = load_success(tmp_path / "one", first_case)
    second, _ = load_success(tmp_path / "two", second_case)

    assert first["case_id"] == first_case["case_id"]
    assert first["lineage_epochs"] == first_path
    assert first["continuity_chain"] == first_chain
    assert first["secret_mod"] == first_secret
    assert second["case_id"] == second_case["case_id"]
    assert second["lineage_epochs"] == second_path
    assert second["continuity_chain"] == second_chain
    assert second["secret_mod"] == second_secret
    assert first["model_frontier_digest"] != second["model_frontier_digest"]
    assert first["evidence_digest"] != second["evidence_digest"]


def test_dynamic_authorized_handoff_variants_defeat_greedy_search(
    tmp_path: Path,
) -> None:
    """Fresh chains must keep a later authorized handoff when the first one blocks deeper recovery."""
    seed = hashlib.sha256(str(tmp_path).encode()).digest()

    def build_variant(label: str) -> tuple[dict, list[str], list[list[str]], str]:
        token = hashlib.sha256(seed + b"handoff-" + label.encode()).hexdigest()[:9]
        case_id = f"authorized-{label}-{token}"
        key = hashlib.sha256(seed + b"handoff-key-" + label.encode()).digest()[:16]
        epochs = [f"root-{token}", f"mid-{token}", f"leaf-{token}"]
        secrets = [20 + seed[0] % 50]
        secrets.append((secrets[-1] + 17 + seed[1] % 19) % PRIME)
        secrets.append((secrets[-1] + 23 + seed[2] % 17) % PRIME)
        first_group = [
            (f"a-{label}-{token}-ops", "ops", 1),
            (f"a-{label}-{token}-legal", "legal", 2),
            (f"a-{label}-{token}-sre", "sre", 3),
        ]
        later_group = [
            (f"z-{label}-{token}-ops", "ops", 4),
            (f"z-{label}-{token}-legal", "legal", 5),
            (f"z-{label}-{token}-sre", "sre", 6),
        ]
        all_holders = [*first_group, *later_group]
        shares: list[dict] = []
        for index, epoch in enumerate(epochs):
            shares.extend(
                polynomial_shares(
                    case_id,
                    key,
                    epoch,
                    secrets[index],
                    [3 + index * 2, 7 + index * 2],
                    all_holders,
                )
            )
        first_names = sorted(holder for holder, _, _ in first_group)
        later_names = sorted(holder for holder, _, _ in later_group)
        lineage = [
            lineage_edge(
                case_id,
                epochs[0],
                epochs[1],
                (secrets[1] - secrets[0]) % PRIME,
                secrets[0],
                secrets[1],
                first_names,
                alternate_holders=[later_names],
            ),
            lineage_edge(
                case_id,
                epochs[1],
                epochs[2],
                (secrets[2] - secrets[1]) % PRIME,
                secrets[1],
                secrets[2],
                first_names,
            ),
        ]
        case = make_case(
            case_id,
            key,
            shares,
            {
                epoch: commitment(case_id, epoch, secret)
                for epoch, secret in zip(epochs, secrets)
            },
            lineage=lineage,
            min_lineage_depth=3,
        )
        return case, epochs, [later_names, first_names], str(secrets[-1])

    one_case, one_epochs, one_chain, one_secret = build_variant("one")
    two_case, two_epochs, two_chain, two_secret = build_variant("two")
    one, _ = load_success(tmp_path / "one", one_case)
    two, _ = load_success(tmp_path / "two", two_case)

    assert one["status"] == "recovered"
    assert one["lineage_epochs"] == one_epochs
    assert one["continuity_chain"] == one_chain
    assert one["secret_mod"] == one_secret
    assert two["status"] == "recovered"
    assert two["lineage_epochs"] == two_epochs
    assert two["continuity_chain"] == two_chain
    assert two["secret_mod"] == two_secret
    assert one["model_frontier_digest"] != two["model_frontier_digest"]
    assert one["evidence_digest"] != two["evidence_digest"]


def test_handoff_seal_order_is_irrelevant_and_chain_tiebreak_is_global(
    tmp_path: Path,
) -> None:
    """Seal-array order cannot choose the handoff; equal-depth states use continuity-chain order."""
    case_id = "authorized-handoff-order"
    key = b"authorized-handoff-order-key"
    root_secret = 41
    child_secret = 70
    holders = [
        ("a-ops", "ops", 1),
        ("a-legal", "legal", 2),
        ("a-sre", "sre", 3),
        ("z-ops", "ops", 4),
        ("z-legal", "legal", 5),
        ("z-sre", "sre", 6),
    ]
    root = polynomial_shares(case_id, key, "root", root_secret, [5, 8], holders)
    child = polynomial_shares(case_id, key, "child", child_secret, [7, 10], holders)
    first = ["a-legal", "a-ops", "a-sre"]
    second = ["z-legal", "z-ops", "z-sre"]
    edge = lineage_edge(
        case_id,
        "root",
        "child",
        child_secret - root_secret,
        root_secret,
        child_secret,
        second,
        alternate_holders=[first],
    )
    case = make_case(
        case_id,
        key,
        [*root, *child],
        {
            "root": commitment(case_id, "root", root_secret),
            "child": commitment(case_id, "child", child_secret),
        },
        lineage=[edge],
        min_lineage_depth=2,
    )
    reordered = copy.deepcopy(case)
    reordered["lineage"][0]["handoff_seals"].reverse()

    report, raw = load_success(tmp_path / "original", case)
    reordered_report, reordered_raw = load_success(tmp_path / "reordered", reordered)
    assert report["continuity_chain"] == [first]
    assert report == reordered_report
    assert raw == reordered_raw


def test_multiple_parent_path_tiebreak_updates_frontier_deterministically(
    tmp_path: Path,
) -> None:
    """Equal-depth DAG paths must use epoch-path then continuity-chain ordering in the frontier state."""
    case_id = "lineage-path-tiebreak"
    key = b"lineage-path-tiebreak-key"
    secrets = {"alpha": 18, "beta": 44, "child": 73}
    alpha_holders = [("a1", "ops", 1), ("a2", "legal", 2), ("a3", "sre", 3)]
    beta_holders = [("b1", "ops", 1), ("b2", "legal", 2), ("b3", "sre", 3)]
    child_holders = [
        ("a1", "ops", 1),
        ("a2", "legal", 2),
        ("a3", "sre", 3),
        ("b1", "ops", 4),
        ("b2", "legal", 5),
        ("b3", "sre", 6),
    ]
    shares = [
        *polynomial_shares(
            case_id, key, "alpha", secrets["alpha"], [2, 5], alpha_holders
        ),
        *polynomial_shares(case_id, key, "beta", secrets["beta"], [3, 7], beta_holders),
        *polynomial_shares(
            case_id, key, "child", secrets["child"], [11, 9], child_holders
        ),
    ]
    lineage = [
        lineage_edge(
            case_id,
            "beta",
            "child",
            29,
            secrets["beta"],
            secrets["child"],
            ["b1", "b2", "b3"],
        ),
        lineage_edge(
            case_id,
            "alpha",
            "child",
            55,
            secrets["alpha"],
            secrets["child"],
            ["a1", "a2", "a3"],
        ),
    ]
    case = make_case(
        case_id,
        key,
        shares,
        {
            epoch: commitment(case_id, epoch, secret)
            for epoch, secret in secrets.items()
        },
        lineage=lineage,
        min_lineage_depth=2,
    )
    reordered = copy.deepcopy(case)
    reordered["lineage"].reverse()

    first, first_raw = load_success(tmp_path / "first", case)
    second, second_raw = load_success(tmp_path / "second", reordered)
    assert first["selected_epoch"] == "child"
    assert first["lineage_epochs"] == ["alpha", "child"]
    assert first["continuity_chain"] == [["a1", "a2", "a3"]]
    assert first_raw == second_raw


def test_refresh_seal_binds_secrets_and_authorized_continuity_witness(
    tmp_path: Path,
) -> None:
    """A transition seal must bind the model secrets and an authorized holder quorum."""
    case_id = "sealed-continuity-choice"
    key = b"sealed-continuity-choice-key"
    root_secret = 73
    child_secret = 92
    holders = [("a", "ops", 1), ("b", "legal", 2), ("c", "sre", 3), ("d", "ops", 4)]
    root = polynomial_shares(case_id, key, "root", root_secret, [5, 9], holders)
    child = polynomial_shares(case_id, key, "child", child_secret, [7, 11], holders)
    edge = lineage_edge(
        case_id,
        "root",
        "child",
        19,
        root_secret,
        child_secret,
        ["a", "b", "c"],
        continuity_roles=["ops", "legal"],
        continuity_quorum=3,
    )
    good = make_case(
        case_id,
        key,
        [*root, *child],
        {
            "root": commitment(case_id, "root", root_secret),
            "child": commitment(case_id, "child", child_secret),
        },
        lineage=[edge],
    )
    wrong_witness = copy.deepcopy(good)
    wrong_witness["lineage"][0]["handoff_seals"] = [
        transition_seal(
            case_id, "root", "child", 19, root_secret, child_secret + 1, ["a", "b", "c"]
        )
    ]

    recovered, _ = load_success(tmp_path / "good", good)
    fallback, _ = load_success(tmp_path / "wrong-witness", wrong_witness)
    assert recovered["selected_epoch"] == "child"
    assert recovered["lineage_epochs"] == ["root", "child"]
    assert recovered["continuity_holders"] == ["a", "b", "c"]
    assert fallback["selected_epoch"] == "root"
    assert fallback["lineage_epochs"] == ["root"]
    assert fallback["continuity_holders"] == []
    assert recovered["model_frontier_digest"] != fallback["model_frontier_digest"]
    assert recovered["evidence_digest"] != fallback["evidence_digest"]


def test_continuity_requires_role_stability_across_epochs(tmp_path: Path) -> None:
    """A holder whose role changed cannot satisfy the edge continuity-role requirement."""
    case_id = "continuity-role-stability"
    key = b"continuity-role-stability-key"
    root_secret = 31
    child_secret = 44
    root = polynomial_shares(
        case_id,
        key,
        "root",
        root_secret,
        [4, 6],
        [("a", "ops", 1), ("b", "legal", 2), ("c", "sre", 3), ("d", "ops", 4)],
    )
    child = polynomial_shares(
        case_id,
        key,
        "child",
        child_secret,
        [8, 10],
        [("a", "ops", 1), ("b", "ops", 2), ("c", "sre", 3), ("d", "legal", 4)],
    )
    edge = lineage_edge(
        case_id,
        "root",
        "child",
        13,
        root_secret,
        child_secret,
        ["a", "b"],
        continuity_roles=["legal"],
        continuity_quorum=2,
    )
    case = make_case(
        case_id,
        key,
        [*root, *child],
        {
            "root": commitment(case_id, "root", root_secret),
            "child": commitment(case_id, "child", child_secret),
        },
        lineage=[edge],
        min_lineage_depth=2,
    )

    report, _ = load_success(tmp_path, case)
    assert report["status"] == "blocked"
    assert report["reason"] == "lineage_not_reached"
    assert report["continuity_holders"] == []


def test_nonwinning_lineage_branch_changes_frontier_not_winner(tmp_path: Path) -> None:
    """A usable secondary refresh branch must change frontier evidence without displacing a deeper chain."""
    case_id = "lineage-frontier-branch"
    key = b"lineage-frontier-branch-key"
    secrets = {"root": 20, "mid": 27, "leaf": 38, "branch": 31}
    group_a = [
        ("keeper-a-ops", "ops", 1),
        ("keeper-a-legal", "legal", 2),
        ("keeper-a-sre", "sre", 3),
    ]
    group_b = [
        ("keeper-b-ops", "ops", 4),
        ("keeper-b-legal", "legal", 5),
        ("keeper-b-sre", "sre", 6),
    ]
    epochs = {
        "root": polynomial_shares(
            case_id, key, "root", secrets["root"], [3, 6], group_a
        ),
        "mid": polynomial_shares(
            case_id, key, "mid", secrets["mid"], [4, 7], [*group_a, *group_b]
        ),
        "leaf": polynomial_shares(
            case_id, key, "leaf", secrets["leaf"], [5, 8], group_b
        ),
        "branch": polynomial_shares(
            case_id, key, "branch", secrets["branch"], [6, 9], group_a
        ),
    }
    commitments = {
        epoch: commitment(case_id, epoch, secret) for epoch, secret in secrets.items()
    }
    base_edges = [
        lineage_edge(
            case_id,
            "root",
            "mid",
            7,
            secrets["root"],
            secrets["mid"],
            ["keeper-a-legal", "keeper-a-ops", "keeper-a-sre"],
        ),
        lineage_edge(
            case_id,
            "mid",
            "leaf",
            11,
            secrets["mid"],
            secrets["leaf"],
            ["keeper-b-legal", "keeper-b-ops", "keeper-b-sre"],
        ),
    ]
    broken = make_case(
        case_id,
        key,
        [share for epoch in epochs.values() for share in epoch],
        commitments,
        lineage=[
            *base_edges,
            lineage_edge(
                case_id,
                "root",
                "branch",
                12,
                secrets["root"],
                secrets["branch"],
                ["keeper-a-legal", "keeper-a-ops", "keeper-a-sre"],
            ),
        ],
        min_lineage_depth=3,
    )
    linked = copy.deepcopy(broken)
    linked["lineage"][-1] = lineage_edge(
        case_id,
        "root",
        "branch",
        11,
        secrets["root"],
        secrets["branch"],
        ["keeper-a-legal", "keeper-a-ops", "keeper-a-sre"],
    )

    first, _ = load_success(tmp_path / "broken", broken)
    second, _ = load_success(tmp_path / "linked", linked)
    for report in (first, second):
        assert report["selected_epoch"] == "leaf"
        assert report["lineage_epochs"] == ["root", "mid", "leaf"]
        assert report["secret_mod"] == str(secrets["leaf"])
    assert first["evaluated_model_count"] == second["evaluated_model_count"]
    assert first["model_frontier_digest"] != second["model_frontier_digest"]
    assert first["evidence_digest"] != second["evidence_digest"]


def test_block_reason_precedence_covers_consensus_policy_and_commitment(
    tmp_path: Path,
) -> None:
    """Blocked reports must preserve precedence through consensus, policy, commitment, and lineage failure."""
    key = b"block-reason-key"

    few_id = "blocked-few"
    few_shares = polynomial_shares(
        few_id,
        key,
        "e",
        20,
        [2, 3],
        [("f1", "ops", 1), ("f2", "legal", 2)],
    )
    few = make_case(few_id, key, few_shares, {"e": commitment(few_id, "e", 20)})

    consensus_id = "blocked-consensus"
    consensus_shares = polynomial_shares(
        consensus_id,
        key,
        "e",
        40,
        [4, 5],
        [("c1", "ops", 1), ("c2", "legal", 2), ("c3", "sre", 3)],
    )
    consensus_shares.append(make_share(consensus_id, key, "c4", "ops", "e", 4, 222))
    consensus = make_case(
        consensus_id,
        key,
        consensus_shares,
        {"e": commitment(consensus_id, "e", 40)},
        max_outliers=0,
    )

    policy_id = "blocked-policy"
    policy_shares = polynomial_shares(
        policy_id,
        key,
        "e",
        60,
        [6, 7],
        [("p1", "ops", 1), ("p2", "ops", 2), ("p3", "ops", 3)],
    )
    policy = make_case(
        policy_id,
        key,
        policy_shares,
        {"e": commitment(policy_id, "e", 60)},
        required_roles=["ops", "legal"],
        role_limits={"ops": 3, "legal": 1},
    )

    mismatch_id = "blocked-commitment"
    mismatch_shares = polynomial_shares(
        mismatch_id,
        key,
        "e",
        80,
        [8, 9],
        [("m1", "ops", 1), ("m2", "legal", 2), ("m3", "sre", 3)],
    )
    mismatch = make_case(
        mismatch_id,
        key,
        mismatch_shares,
        {"e": commitment(mismatch_id, "e", 81)},
    )

    lineage_id = "blocked-lineage"
    root_secret = 25
    child_secret = 90
    root_shares = polynomial_shares(
        lineage_id,
        key,
        "root",
        root_secret,
        [3, 2],
        [("r1", "ops", 1), ("r2", "legal", 2), ("r3", "sre", 3)],
    )
    child_shares = polynomial_shares(
        lineage_id,
        key,
        "child",
        child_secret,
        [5, 4],
        [("r1", "ops", 1), ("r2", "legal", 2), ("r3", "sre", 3)],
    )
    lineage = make_case(
        lineage_id,
        key,
        [*root_shares, *child_shares],
        {
            "root": commitment(lineage_id, "root", root_secret),
            "child": commitment(lineage_id, "child", child_secret),
        },
        lineage=[
            lineage_edge(
                lineage_id,
                "root",
                "child",
                7,
                root_secret,
                child_secret,
                ["r1", "r2", "r3"],
            )
        ],
        min_lineage_depth=2,
    )

    expected = [
        (few, "not_enough_valid_shares"),
        (consensus, "consensus_not_reached"),
        (policy, "role_requirement_unsatisfied"),
        (mismatch, "commitment_mismatch"),
        (lineage, "lineage_not_reached"),
    ]
    for index, (case, reason) in enumerate(expected):
        report, _ = load_success(tmp_path / str(index), case)
        assert report["status"] == "blocked"
        assert report["reason"] == reason


def test_dynamic_variant_defeats_hardcoded_solution(tmp_path: Path) -> None:
    """Fresh multi-epoch chains, secrets, supports, outliers, and digests must be computed at verifier time."""
    seed = hashlib.sha256(str(tmp_path).encode()).digest()
    key = hashlib.sha256(seed + b"key").digest()[:16]

    def dynamic_case(
        label: str,
        depth: int,
        support_count: int,
        outlier_count: int,
    ) -> tuple[dict, int, str, list[str]]:
        token = hashlib.sha256(seed + label.encode()).hexdigest()[:10]
        case_id = f"fresh-{label}-{token}"
        epochs = [
            f"epoch-{label}-{index}-{token[index : index + 5]}"
            for index in range(depth)
        ]
        secrets = [30 + (int(token[:6], 16) % 190)]
        offsets: list[int] = []
        for index in range(1, depth):
            offset = 1 + seed[(index + len(label)) % len(seed)] % 31
            offsets.append(offset)
            secrets.append((secrets[-1] + offset) % PRIME)

        shares: list[dict] = []
        commitments: dict[str, str] = {}
        lineage: list[dict] = []
        edge_groups = [
            [
                (f"{label}-e{edge}-h1", "ops"),
                (f"{label}-e{edge}-h2", "legal"),
                (f"{label}-e{edge}-h3", "sre"),
            ]
            for edge in range(max(0, depth - 1))
        ]
        for index, epoch in enumerate(epochs):
            if depth == 1:
                named_roles = [
                    (f"{label}-root-h1", "ops"),
                    (f"{label}-root-h2", "legal"),
                    (f"{label}-root-h3", "sre"),
                ]
            elif index == 0:
                named_roles = edge_groups[0]
            elif index == depth - 1:
                named_roles = list(edge_groups[index - 1])
                for extra in range(max(0, support_count - 3)):
                    named_roles.append((f"{label}-extra{extra}", "ops"))
            else:
                named_roles = [*edge_groups[index - 1], *edge_groups[index]]
            coeffs = [
                1 + seed[(index + 2) % len(seed)] % 29,
                1 + seed[(index + 7) % len(seed)] % 31,
            ]
            holders = [
                (holder, role, holder_index)
                for holder_index, (holder, role) in enumerate(named_roles, start=1)
            ]
            shares.extend(
                polynomial_shares(case_id, key, epoch, secrets[index], coeffs, holders)
            )
            commitments[epoch] = commitment(case_id, epoch, secrets[index])
            if index:
                continuity = sorted(holder for holder, _ in edge_groups[index - 1])
                lineage.append(
                    lineage_edge(
                        case_id,
                        epochs[index - 1],
                        epoch,
                        offsets[index - 1],
                        secrets[index - 1],
                        secrets[index],
                        continuity,
                    )
                )

        terminal_epoch = epochs[-1]
        terminal_secret = secrets[-1]
        terminal_support = [
            share for share in shares if share["epoch"] == terminal_epoch
        ]
        # Reuse the actual terminal polynomial through any threshold subset when adding noise.
        seed_points = terminal_support[:3]
        for i in range(outlier_count):
            x = support_count + i + 1
            expected_y = interpolate(seed_points, x, PRIME)
            shares.append(
                make_share(
                    case_id,
                    key,
                    f"{label}-noise{i}",
                    "ops",
                    terminal_epoch,
                    x,
                    (expected_y + 17 + i) % PRIME,
                )
            )
        case = make_case(
            case_id,
            key,
            shares,
            commitments,
            max_outliers=outlier_count,
            lineage=lineage,
            min_lineage_depth=depth,
        )
        return case, terminal_secret, terminal_epoch, epochs

    baseline, baseline_secret, baseline_epoch, baseline_chain = dynamic_case(
        "base", 1, 3, 0
    )
    fresh_one, secret_one, epoch_one, chain_one = dynamic_case("one", 2, 4, 1)
    fresh_two, secret_two, epoch_two, chain_two = dynamic_case("two", 3, 5, 2)

    base_report, _ = load_success(tmp_path / "base", baseline)
    report_one, _ = load_success(tmp_path / "one", fresh_one)
    report_two, _ = load_success(tmp_path / "two", fresh_two)

    assert base_report["case_id"] == baseline["case_id"]
    assert base_report["selected_epoch"] == baseline_epoch
    assert base_report["lineage_epochs"] == baseline_chain
    assert base_report["secret_mod"] == str(baseline_secret)
    assert report_one["case_id"] == fresh_one["case_id"]
    assert report_one["selected_epoch"] == epoch_one
    assert report_one["lineage_epochs"] == chain_one
    assert report_one["continuity_holders"] == ["one-e0-h1", "one-e0-h2", "one-e0-h3"]
    assert report_one["continuity_chain"] == [["one-e0-h1", "one-e0-h2", "one-e0-h3"]]
    assert report_one["secret_mod"] == str(secret_one)
    assert report_one["support_share_count"] == 4
    assert len(report_one["outlier_holders"]) == 1
    assert report_two["case_id"] == fresh_two["case_id"]
    assert report_two["selected_epoch"] == epoch_two
    assert report_two["lineage_epochs"] == chain_two
    assert report_two["continuity_holders"] == ["two-e1-h1", "two-e1-h2", "two-e1-h3"]
    assert report_two["continuity_chain"] == [
        ["two-e0-h1", "two-e0-h2", "two-e0-h3"],
        ["two-e1-h1", "two-e1-h2", "two-e1-h3"],
    ]
    assert report_two["secret_mod"] == str(secret_two)
    assert report_two["support_share_count"] == 5
    assert len(report_two["outlier_holders"]) == 2
    assert (
        len(
            {
                base_report["valid_share_count"],
                report_one["valid_share_count"],
                report_two["valid_share_count"],
            }
        )
        == 3
    )
    assert (
        len(
            {
                base_report["support_share_count"],
                report_one["support_share_count"],
                report_two["support_share_count"],
            }
        )
        == 3
    )
    assert (
        len(
            {
                base_report["model_frontier_digest"],
                report_one["model_frontier_digest"],
                report_two["model_frontier_digest"],
            }
        )
        == 3
    )
    assert (
        len(
            {
                base_report["evidence_digest"],
                report_one["evidence_digest"],
                report_two["evidence_digest"],
            }
        )
        == 3
    )


def test_invalid_schema_and_prime_preserve_existing_output(tmp_path: Path) -> None:
    """Malformed schema, role-policy constraints, types, bounds, identity, epochs, and modulus must exit 2 without touching output."""
    case_id = "invalid-input"
    key = b"invalid-input-key"
    secret = 44
    shares = polynomial_shares(
        case_id,
        key,
        "e",
        secret,
        [3, 4],
        [("i1", "ops", 1), ("i2", "legal", 2), ("i3", "sre", 3)],
    )
    base = make_case(case_id, key, shares, {"e": commitment(case_id, "e", secret)})

    invalid_cases: list[dict] = []
    extra = copy.deepcopy(base)
    extra["unexpected"] = True
    invalid_cases.append(extra)
    wrong_type = copy.deepcopy(base)
    wrong_type["max_outliers"] = "0"
    invalid_cases.append(wrong_type)
    nested_wrong_type = copy.deepcopy(base)
    nested_wrong_type["role_limits"]["ops"] = "1"
    invalid_cases.append(nested_wrong_type)
    duplicate_required_role = copy.deepcopy(base)
    duplicate_required_role["required_roles"] = ["ops", "legal", "ops"]
    invalid_cases.append(duplicate_required_role)
    empty_required_role = copy.deepcopy(base)
    empty_required_role["required_roles"] = ["ops", "", "sre"]
    invalid_cases.append(empty_required_role)
    empty_role_limit_key = copy.deepcopy(base)
    empty_role_limit_key["role_limits"][""] = 0
    invalid_cases.append(empty_role_limit_key)
    negative_role_limit = copy.deepcopy(base)
    negative_role_limit["role_limits"]["ops"] = -1
    invalid_cases.append(negative_role_limit)
    share_wrong_type = copy.deepcopy(base)
    share_wrong_type["shares"][0]["x"] = "1"
    invalid_cases.append(share_wrong_type)
    boolean_wrong_type = copy.deepcopy(base)
    boolean_wrong_type["threshold"] = True
    invalid_cases.append(boolean_wrong_type)
    negative = copy.deepcopy(base)
    negative["max_outliers"] = -1
    invalid_cases.append(negative)
    composite = copy.deepcopy(base)
    composite["prime"] = 15
    invalid_cases.append(composite)
    duplicate_holder = copy.deepcopy(base)
    duplicate = copy.deepcopy(duplicate_holder["shares"][0])
    duplicate["x"] = 4
    duplicate["y"] = y_at(secret, [3, 4], 4)
    duplicate["mac"] = sign(case_id, key, duplicate)
    duplicate_holder["shares"].append(duplicate)
    invalid_cases.append(duplicate_holder)
    extra_share_field = copy.deepcopy(base)
    extra_share_field["shares"][0]["extra"] = 1
    invalid_cases.append(extra_share_field)
    unknown_epoch = copy.deepcopy(base)
    unknown_epoch["shares"][0]["epoch"] = "missing"
    unknown_epoch["shares"][0]["mac"] = sign(case_id, key, unknown_epoch["shares"][0])
    invalid_cases.append(unknown_epoch)
    lineage_depth_type = copy.deepcopy(base)
    lineage_depth_type["min_lineage_depth"] = "1"
    invalid_cases.append(lineage_depth_type)
    lineage_not_array = copy.deepcopy(base)
    lineage_not_array["lineage"] = {}
    invalid_cases.append(lineage_not_array)

    too_many_commitments = copy.deepcopy(base)
    for index in range(12):
        epoch = f"extra-{index}"
        too_many_commitments["commitments"][epoch] = commitment(case_id, epoch, index)
    invalid_cases.append(too_many_commitments)

    lineage_base = copy.deepcopy(base)
    lineage_base["commitments"].update(
        {
            "f": commitment(case_id, "f", 55),
            "g": commitment(case_id, "g", 66),
        }
    )
    edge_ef = lineage_edge(
        case_id,
        "e",
        "f",
        1,
        secret,
        55,
        ["i1"],
        continuity_roles=[],
        continuity_quorum=1,
    )
    lineage_offset_type = copy.deepcopy(lineage_base)
    lineage_offset_type["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_offset_type["lineage"][0]["offset"] = "1"
    invalid_cases.append(lineage_offset_type)
    lineage_offset_bound = copy.deepcopy(lineage_base)
    lineage_offset_bound["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_offset_bound["lineage"][0]["offset"] = PRIME
    invalid_cases.append(lineage_offset_bound)
    lineage_unknown = copy.deepcopy(lineage_base)
    lineage_unknown["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_unknown["lineage"][0]["parent"] = "missing"
    invalid_cases.append(lineage_unknown)
    lineage_duplicate_edge = copy.deepcopy(lineage_base)
    duplicate = lineage_edge(
        case_id,
        "e",
        "g",
        1,
        secret,
        66,
        ["i1"],
        continuity_roles=[],
        continuity_quorum=1,
    )
    lineage_duplicate_edge["lineage"] = [
        copy.deepcopy(duplicate),
        copy.deepcopy(duplicate),
    ]
    invalid_cases.append(lineage_duplicate_edge)
    lineage_cycle = copy.deepcopy(lineage_base)
    lineage_cycle["lineage"] = [
        copy.deepcopy(edge_ef),
        lineage_edge(
            case_id,
            "f",
            "e",
            2,
            55,
            secret,
            ["i1"],
            continuity_roles=[],
            continuity_quorum=1,
        ),
    ]
    invalid_cases.append(lineage_cycle)
    lineage_extra_field = copy.deepcopy(lineage_base)
    lineage_extra_field["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_extra_field["lineage"][0]["extra"] = True
    invalid_cases.append(lineage_extra_field)
    continuity_roles_type = copy.deepcopy(lineage_base)
    continuity_roles_type["lineage"] = [copy.deepcopy(edge_ef)]
    continuity_roles_type["lineage"][0]["continuity_roles"] = "ops"
    invalid_cases.append(continuity_roles_type)
    continuity_roles_duplicate = copy.deepcopy(lineage_base)
    continuity_roles_duplicate["lineage"] = [copy.deepcopy(edge_ef)]
    continuity_roles_duplicate["lineage"][0]["continuity_roles"] = ["ops", "ops"]
    continuity_roles_duplicate["lineage"][0]["continuity_quorum"] = 2
    invalid_cases.append(continuity_roles_duplicate)
    continuity_quorum_type = copy.deepcopy(lineage_base)
    continuity_quorum_type["lineage"] = [copy.deepcopy(edge_ef)]
    continuity_quorum_type["lineage"][0]["continuity_quorum"] = "1"
    invalid_cases.append(continuity_quorum_type)
    continuity_quorum_bound = copy.deepcopy(lineage_base)
    continuity_quorum_bound["lineage"] = [copy.deepcopy(edge_ef)]
    continuity_quorum_bound["lineage"][0]["continuity_quorum"] = 0
    invalid_cases.append(continuity_quorum_bound)
    continuity_roles_exceed_quorum = copy.deepcopy(lineage_base)
    continuity_roles_exceed_quorum["lineage"] = [copy.deepcopy(edge_ef)]
    continuity_roles_exceed_quorum["lineage"][0]["continuity_roles"] = ["ops", "legal"]
    invalid_cases.append(continuity_roles_exceed_quorum)
    lineage_bad_seal = copy.deepcopy(lineage_base)
    lineage_bad_seal["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_bad_seal["lineage"][0]["handoff_seals"] = ["sha256:ABC"]
    invalid_cases.append(lineage_bad_seal)
    lineage_empty_seals = copy.deepcopy(lineage_base)
    lineage_empty_seals["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_empty_seals["lineage"][0]["handoff_seals"] = []
    invalid_cases.append(lineage_empty_seals)
    lineage_duplicate_seals = copy.deepcopy(lineage_base)
    lineage_duplicate_seals["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_duplicate_seals["lineage"][0]["handoff_seals"].append(
        lineage_duplicate_seals["lineage"][0]["handoff_seals"][0]
    )
    invalid_cases.append(lineage_duplicate_seals)
    lineage_seals_wrong_type = copy.deepcopy(lineage_base)
    lineage_seals_wrong_type["lineage"] = [copy.deepcopy(edge_ef)]
    lineage_seals_wrong_type["lineage"][0]["handoff_seals"] = "sha256:" + "0" * 64
    invalid_cases.append(lineage_seals_wrong_type)
    lineage_depth_bound = copy.deepcopy(lineage_base)
    lineage_depth_bound["min_lineage_depth"] = 4
    invalid_cases.append(lineage_depth_bound)

    for index, case in enumerate(invalid_cases):
        folder = tmp_path / str(index)
        folder.mkdir()
        input_path = folder / "case.json"
        output_path = folder / "report.json"
        input_path.write_text(json.dumps(case), encoding="utf-8")
        output_path.write_bytes(b"keep-this-output\n")
        result = subprocess.run(
            [str(BIN), str(input_path), str(output_path)],
            cwd=APP,
            env=child_env(),
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr == "vaultquorum: invalid input\n"
        assert output_path.read_bytes() == b"keep-this-output\n"


def test_wrong_argument_count_exits_2() -> None:
    """The reusable CLI must reject every argument count other than input and output."""
    for argv in (
        [str(BIN)],
        [str(BIN), "/tmp/a"],
        [str(BIN), "/tmp/a", "/tmp/b", "/tmp/c"],
    ):
        result = subprocess.run(
            argv, cwd=APP, env=child_env(), text=True, capture_output=True, timeout=10
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr == "vaultquorum: invalid input\n"


def test_repeated_run_is_byte_identical(tmp_path: Path) -> None:
    """The same robust incident bundle must produce byte-identical JSON and digest on repeated runs."""
    case_id = "deterministic-robust"
    key = b"deterministic-robust-key"
    epoch = "stable"
    secret = 137
    shares = polynomial_shares(
        case_id,
        key,
        epoch,
        secret,
        [14, 6],
        [("d1", "ops", 1), ("d2", "legal", 2), ("d3", "sre", 3), ("d4", "ops", 4)],
    )
    shares.append(make_share(case_id, key, "d5", "ops", epoch, 5, 222))
    case = make_case(
        case_id,
        key,
        shares,
        {epoch: commitment(case_id, epoch, secret)},
        max_outliers=1,
    )

    first, first_raw = load_success(tmp_path / "first", case)
    second, second_raw = load_success(tmp_path / "second", case)
    assert first == second
    assert first_raw == second_raw


def test_reusable_cli_artifact_is_elf_after_clean_build() -> None:
    """A clean build must leave the requested executable Go ELF artifact at the documented path."""
    BIN.unlink(missing_ok=True)
    result = subprocess.run(
        ["/app/build.sh"], cwd=APP, text=True, capture_output=True, timeout=60
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert BIN.exists() and os.access(BIN, os.X_OK)
    assert BIN.read_bytes()[:4] == b"\x7fELF"
    metadata = subprocess.run(
        ["go", "version", "-m", str(BIN)], text=True, capture_output=True, timeout=10
    )
    assert metadata.returncode == 0 and "\tpath\tvaultquorum" in metadata.stdout
