import email.parser
import email.utils
import hashlib
import ipaddress
import json
import re
import stat
import struct
import subprocess
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

APP = Path("/app")
CHANGE = APP / "change"
RIS = CHANGE / "ris"
DECISIONS = CHANGE / "decisions"
ROUNDS = ("01", "02", "03")
FAMILIES = {
    "ipv4": ("193.0.0.0/21", "v4"),
    "ipv6": ("2001:67c:2e8::/48", "v6"),
}
EVIDENCE = [
    RIS / round_id / f"{family}.{suffix}"
    for round_id in ROUNDS
    for family in FAMILIES
    for suffix in ("headers", "json", "request.json", "meta.json")
]
ROUND_DECISIONS = [DECISIONS / f"{round_id}.json" for round_id in ROUNDS]
CORE = [
    CHANGE / "acquisition-checkpoints.jsonl",
    CHANGE / "acquisition-summary.json",
    CHANGE / "acquisition.jsonl",
    CHANGE / "artifact-graph.json",
    CHANGE / "bundle-index.json",
    CHANGE / "bundle-merkle.json",
    CHANGE / "bundle-proofs.json",
    CHANGE / "commit.json",
    CHANGE / "consensus-certificate.json",
    CHANGE / "custody.jsonl",
    CHANGE / "candidate-delta.json",
    CHANGE / "candidate.patch",
    CHANGE / "capture-bindings.jsonl",
    CHANGE / "decision.json",
    CHANGE / "frr-validate-01.log",
    CHANGE / "frr-validate-02.log",
    CHANGE / "frr.conf",
    CHANGE / "gate-executions.jsonl",
    CHANGE / "render-provenance.json",
    CHANGE / "rollback.conf",
    CHANGE / "quorum.json",
    CHANGE / "release-authorization.json",
    CHANGE / "session.json",
    CHANGE / "signing-key.json",
    CHANGE / "source-inputs.sha256",
    CHANGE / "signing-public.pem",
    CHANGE / "policy-attestation.json",
    CHANGE / "rollback-validate-01.log",
    CHANGE / "rollback-validate-02.log",
    CHANGE / "rollback-validation.json",
    CHANGE / "round-manifests.jsonl",
    CHANGE / "transport-ledger.jsonl",
    CHANGE / "validation.json",
    CHANGE / "validator-attestation.json",
]
NON_RECEIPT = sorted([*EVIDENCE, *ROUND_DECISIONS, *CORE])
ALL_FILES = [*NON_RECEIPT, CHANGE / "receipt.sha256", CHANGE / "receipt.sig"]
SOURCE_DIGESTS = {
    "running": "ce8359e621c1bdd63bed0ca1c6ec108c82bcf53cc5567e5d1b13012ab6770113",
    "policy": "163b4e05132c4a79f5fc9a933b35f0fd68476ea096e91155fd53a6038ed7120e",
    "inventory": "b0eb746c3dbb07162bfa6ccc364d976b276adc13135f283396e5dc6795071925",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=dict)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(APP).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def parse_headers(path: Path):
    raw = path.read_bytes()
    assert raw.count(b"HTTP/") == 1
    assert raw.endswith((b"\r\n\r\n", b"\n\n"))
    lines = raw.splitlines(keepends=True)
    assert re.fullmatch(rb"HTTP/\S+ 2\d\d .+\r?\n", lines[0])
    headers = email.parser.BytesHeaderParser().parsebytes(b"".join(lines[1:]))
    assert headers.get_content_type() == "application/json"
    return headers


def parse_manifest(path: Path) -> list[tuple[str, Path]]:
    result = []
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (/app/.+)", line)
        assert match, f"invalid manifest line: {line}"
        digest, path_text = match.groups()
        result.append((digest, Path(path_text)))
    return result


def test_change_tree_is_closed_private_and_link_safe():
    """The bundle contains only documented directories and secure artifacts."""
    expected_dirs = {
        CHANGE,
        RIS,
        DECISIONS,
        *(RIS / round_id for round_id in ROUNDS),
    }
    observed_dirs = {path for path in CHANGE.rglob("*") if path.is_dir()}
    observed_dirs.add(CHANGE)
    assert observed_dirs == expected_dirs
    observed_files = {path for path in CHANGE.rglob("*") if path.is_file()}
    assert observed_files == set(ALL_FILES)
    for directory in expected_dirs:
        info = directory.lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert not directory.is_symlink()
        assert stat.S_IMODE(info.st_mode) == 0o750
    for path in ALL_FILES:
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode), f"not regular: {path}"
        assert not path.is_symlink(), f"unsafe symlink: {path}"
        assert info.st_nlink == 1, f"multiply linked: {path}"
        assert stat.S_IMODE(info.st_mode) == 0o640, f"wrong mode: {path}"


def test_protected_router_inputs_remain_untouched():
    """Running state, policy fragments, and inventory retain shipped bytes."""
    running = [APP / "etc/frr/running.conf"]
    policy = sorted((APP / "policy").rglob("*.conf"))
    inventory = sorted((APP / "inventory").glob("*.csv"))
    assert tree_digest(running) == SOURCE_DIGESTS["running"]
    assert len(policy) == 15
    assert tree_digest(policy) == SOURCE_DIGESTS["policy"]
    assert len(inventory) == 3
    assert tree_digest(inventory) == SOURCE_DIGESTS["inventory"]


def test_rollback_preserves_the_running_configuration():
    """The rollback is byte-identical to the untouched running baseline."""
    assert (CHANGE / "rollback.conf").read_bytes() == (
        APP / "etc/frr/running.conf"
    ).read_bytes()


@pytest.mark.parametrize("round_id", ROUNDS)
@pytest.mark.parametrize(
    ("family", "resource", "visibility_key"),
    [
        pytest.param("ipv4", "193.0.0.0/21", "v4", id="ipv4"),
        pytest.param("ipv6", "2001:67c:2e8::/48", "v6", id="ipv6"),
    ],
)
def test_each_round_has_coherent_live_evidence(
    round_id, family, resource, visibility_key
):
    """Every capture is wall-clock fresh and retains the real RIPE v3.4 schema."""
    payload = load_json(RIS / round_id / f"{family}.json")
    headers = parse_headers(RIS / round_id / f"{family}.headers")
    fetched_at = email.utils.parsedate_to_datetime(headers["Date"]).astimezone(
        timezone.utc
    )
    assert abs((datetime.now(timezone.utc) - fetched_at).total_seconds()) <= 45 * 60
    query_time = datetime.fromisoformat(
        payload["data"]["query_time"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    assert query_time <= fetched_at
    assert (fetched_at - query_time).total_seconds() <= 12 * 60 * 60
    assert {
        "messages", "see_also", "version", "data_call_name",
        "data_call_status", "cached", "query_id", "process_time", "server_id",
        "build_version", "pipeline", "status", "status_code", "time", "data",
    } <= payload.keys()
    assert payload["version"] == "3.4"
    assert payload["data_call_name"] == "routing-status"
    assert payload["data_call_status"] == "supported"
    assert payload["status"] == "ok"
    assert payload["status_code"] == 200
    assert isinstance(payload["messages"], list)
    assert isinstance(payload["see_also"], list)
    assert isinstance(payload["cached"], bool)
    assert isinstance(payload["query_id"], str) and payload["query_id"]
    assert isinstance(payload["process_time"], int | float)
    assert payload["process_time"] >= 0
    assert isinstance(payload["server_id"], str) and payload["server_id"]
    assert isinstance(payload["build_version"], str) and payload["build_version"]
    assert isinstance(payload["pipeline"], str) and payload["pipeline"]
    assert isinstance(payload["time"], str) and payload["time"]
    assert set(payload["data"]) == {
        "first_seen", "last_seen", "visibility", "origins",
        "less_specifics", "more_specifics", "resource", "query_time",
    }
    assert payload["data"]["resource"] == resource
    for seen_key in ("first_seen", "last_seen"):
        seen = payload["data"][seen_key]
        assert set(seen) == {"prefix", "origin", "time"}
        ipaddress.ip_network(seen["prefix"])
        assert re.fullmatch(r"\d+", seen["origin"])
        datetime.fromisoformat(seen["time"].replace("Z", "+00:00"))
    origins = payload["data"]["origins"]
    assert isinstance(origins, list) and origins
    for origin in origins:
        assert set(origin) == {"origin", "route_objects"}
        assert isinstance(origin["origin"], int) and origin["origin"] > 0
        assert isinstance(origin["route_objects"], list)
        assert all(
            isinstance(route_object, str) and route_object
            for route_object in origin["route_objects"]
        )
    for specificity in ("less_specifics", "more_specifics"):
        entries = payload["data"][specificity]
        assert isinstance(entries, list)
        for entry in entries:
            assert set(entry) == {"prefix", "origin"}
            ipaddress.ip_network(entry["prefix"])
            assert isinstance(entry["origin"], int) and entry["origin"] > 0
    assert set(payload["data"]["visibility"]) == {"v4", "v6"}
    for family_visibility in payload["data"]["visibility"].values():
        assert set(family_visibility) == {
            "ris_peers_seeing", "total_ris_peers",
        }
        assert all(
            isinstance(value, int) and value >= 0
            for value in family_visibility.values()
        )
    visibility = payload["data"]["visibility"][visibility_key]
    assert visibility["total_ris_peers"] > 0
    assert 0 <= visibility["ris_peers_seeing"] <= visibility["total_ris_peers"]


def test_transfer_metadata_is_live_ordered_and_byte_coherent():
    """Per-request client telemetry proves HTTPS transfer and byte provenance."""
    previous_completion = None
    acquisition_ids = set()
    sequence = 0
    for round_id in ROUNDS:
        for family, (resource, _) in FAMILIES.items():
            sequence += 1
            metadata = load_json(RIS / round_id / f"{family}.meta.json")
            assert list(metadata) == [
                "acquisition_id", "sequence", "round", "family",
                "requested_url", "effective_url", "started_at", "completed_at",
                "status_code", "content_type", "remote_ip", "tls_verified",
                "http_version", "redirects", "bytes_downloaded", "duration_ms",
                "request_sha256", "headers_sha256", "body_sha256",
                "semantic_sha256",
            ]
            acquisition_ids.add(metadata["acquisition_id"])
            assert uuid.UUID(metadata["acquisition_id"]).version == 4
            assert str(uuid.UUID(metadata["acquisition_id"])) == metadata["acquisition_id"]
            assert (metadata["sequence"], metadata["round"], metadata["family"]) == (
                sequence, round_id, family
            )
            for key in ("requested_url", "effective_url"):
                parsed = urllib.parse.urlsplit(metadata[key])
                assert parsed.scheme == "https"
                assert parsed.hostname == "stat.ripe.net"
                assert parsed.path == "/data/routing-status/data.json"
                assert urllib.parse.parse_qs(parsed.query, strict_parsing=True) == {
                    "resource": [resource]
                }
            started = datetime.strptime(
                metadata["started_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc)
            completed = datetime.strptime(
                metadata["completed_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc)
            assert completed >= started
            if previous_completion is not None:
                assert started >= previous_completion
            previous_completion = completed
            http_date = email.utils.parsedate_to_datetime(
                parse_headers(RIS / round_id / f"{family}.headers")["Date"]
            ).astimezone(timezone.utc)
            assert (started.replace(microsecond=0).timestamp() - 300
                    <= http_date.timestamp()
                    <= completed.replace(microsecond=0).timestamp() + 300)
            assert 200 <= metadata["status_code"] <= 299
            assert metadata["content_type"].lower().startswith("application/json")
            ipaddress.ip_address(metadata["remote_ip"])
            assert metadata["tls_verified"] is True
            assert metadata["http_version"] == "1.1"
            assert isinstance(metadata["redirects"], int)
            assert 0 <= metadata["redirects"] <= 3
            body = RIS / round_id / f"{family}.json"
            headers = RIS / round_id / f"{family}.headers"
            assert metadata["bytes_downloaded"] == body.stat().st_size
            elapsed_ms = int((completed - started).total_seconds() * 1000)
            assert isinstance(metadata["duration_ms"], int)
            assert 0 <= metadata["duration_ms"] <= elapsed_ms + 1000
            assert metadata["headers_sha256"] == sha256(headers)
            assert metadata["body_sha256"] == sha256(body)
            request = load_json(RIS / round_id / f"{family}.request.json")
            assert metadata["request_sha256"] == request["request_sha256"]
            semantic = json.dumps(
                load_json(body), sort_keys=True, ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            assert metadata["semantic_sha256"] == hashlib.sha256(
                b"RIS-JSON-SEMANTIC-V1\0" + semantic
            ).hexdigest()
    assert len(acquisition_ids) == 1


def test_evidence_rounds_obey_acquisition_chronology():
    """Header dates establish the documented within- and cross-round order."""
    dates = {}
    for round_id in ROUNDS:
        for family in FAMILIES:
            headers = parse_headers(RIS / round_id / f"{family}.headers")
            dates[round_id, family] = email.utils.parsedate_to_datetime(
                headers["Date"]
            ).astimezone(timezone.utc)
        assert dates[round_id, "ipv4"] <= dates[round_id, "ipv6"]
    for family in FAMILIES:
        assert (
            dates["01", family]
            <= dates["02", family]
            <= dates["03", family]
        )
    assert (dates["03", "ipv6"] - dates["01", "ipv4"]).total_seconds() <= 20 * 60


def test_acquisition_ledger_is_ordered_coherent_and_hash_chained():
    """The six evidence captures form the documented authenticated JSONL chain."""
    path = CHANGE / "acquisition.jsonl"
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 6
    previous = "0" * 64
    expected_pairs = [
        (round_id, family)
        for round_id in ROUNDS
        for family in FAMILIES
    ]
    for sequence, (line, pair) in enumerate(
        zip(lines, expected_pairs, strict=True), start=1
    ):
        entry = json.loads(line, object_pairs_hook=dict)
        assert list(entry) == [
            "acquisition_id",
            "sequence",
            "round",
            "family",
            "resource",
            "http_date",
            "query_time",
            "request_sha256", "metadata_sha256",
            "headers_sha256",
            "body_sha256", "semantic_sha256",
            "previous_sha256",
            "entry_sha256",
        ]
        round_id, family = pair
        resource = FAMILIES[family][0]
        headers_path = RIS / round_id / f"{family}.headers"
        body_path = RIS / round_id / f"{family}.json"
        metadata_path = RIS / round_id / f"{family}.meta.json"
        metadata = load_json(metadata_path)
        request = load_json(RIS / round_id / f"{family}.request.json")
        headers = parse_headers(headers_path)
        payload = load_json(body_path)
        assert entry["sequence"] == sequence
        assert entry["acquisition_id"] == metadata["acquisition_id"]
        assert (entry["round"], entry["family"]) == pair
        assert entry["resource"] == resource
        assert entry["http_date"] == headers["Date"]
        assert entry["query_time"] == payload["data"]["query_time"]
        assert entry["request_sha256"] == request["request_sha256"]
        assert entry["metadata_sha256"] == sha256(metadata_path)
        assert entry["headers_sha256"] == sha256(headers_path)
        assert entry["body_sha256"] == sha256(body_path)
        assert entry["semantic_sha256"] == metadata["semantic_sha256"]
        assert entry["previous_sha256"] == previous
        canonical = json.dumps(
            dict(list(entry.items())[:13]),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        previous = hashlib.sha256(b"RIS-ACQUISITION-V1\0" + canonical).hexdigest()
        assert entry["entry_sha256"] == previous
        assert line == json.dumps(
            entry, ensure_ascii=False, separators=(",", ":")
        )


def test_session_and_request_intent_chain_precede_and_bind_transfers():
    """Session identity and six request intents form an authenticated chain."""
    session = load_json(CHANGE / "session.json")
    assert list(session) == [
        "acquisition_id", "change_id", "router", "endpoint", "user_agent",
        "started_at", "policy_sha256",
    ]
    assert session["change_id"] == "CHG-RIS-EDGE-042"
    assert session["router"] == "edge-ams-01"
    assert session["endpoint"] == (
        "https://stat.ripe.net/data/routing-status/data.json"
    )
    assert all(value in session["user_agent"] for value in (
        session["router"], session["change_id"]
    ))
    assert session["policy_sha256"] == sha256(APP / "policy/visibility.conf")
    session_started = datetime.strptime(
        session["started_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    first_started = datetime.strptime(
        load_json(RIS / "01/ipv4.meta.json")["started_at"],
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ).replace(tzinfo=timezone.utc)
    assert session_started <= first_started
    previous = "0" * 64
    sequence = 0
    for round_id in ROUNDS:
        for family, (resource, _) in FAMILIES.items():
            sequence += 1
            request = load_json(RIS / round_id / f"{family}.request.json")
            assert list(request) == [
                "acquisition_id", "sequence", "round", "family", "resource",
                "url", "user_agent", "session_sha256",
                "previous_request_sha256",
                "request_sha256",
            ]
            assert request == {
                "acquisition_id": session["acquisition_id"],
                "sequence": sequence,
                "round": round_id,
                "family": family,
                "resource": resource,
                "url": load_json(
                    RIS / round_id / f"{family}.meta.json"
                )["requested_url"],
                "user_agent": session["user_agent"],
                "session_sha256": sha256(CHANGE / "session.json"),
                "previous_request_sha256": previous,
                "request_sha256": request["request_sha256"],
            }
            canonical_keys = [
                "acquisition_id", "sequence", "round", "family", "resource",
                "url", "user_agent", "session_sha256",
                "previous_request_sha256",
            ]
            canonical = json.dumps(
                {key: request[key] for key in canonical_keys},
                separators=(",", ":"),
            ).encode()
            previous = hashlib.sha256(
                b"RIS-REQUEST-V2\0" + canonical
            ).hexdigest()
            assert request["request_sha256"] == previous


def test_round_checkpoints_bind_complete_rounds_and_acquisition_tails():
    """Every completed evidence round has its own chained checkpoint."""
    acquisition = [
        json.loads(line)
        for line in (CHANGE / "acquisition.jsonl").read_text().splitlines()
    ]
    lines = (
        CHANGE / "acquisition-checkpoints.jsonl"
    ).read_text().splitlines()
    assert len(lines) == 3
    previous = "0" * 64
    for number, (round_id, line) in enumerate(
        zip(ROUNDS, lines, strict=True), start=1
    ):
        entry = json.loads(line, object_pairs_hook=dict)
        assert list(entry) == [
            "round", "last_sequence", "round_evidence_sha256",
            "request_tail_sha256", "session_sha256",
            "acquisition_tail_sha256", "previous_sha256", "entry_sha256",
        ]
        digest = hashlib.sha256(b"RIS-ROUND-EVIDENCE-V1\0")
        for family in FAMILIES:
            for suffix in ("request.json", "headers", "json", "meta.json"):
                digest.update(hashlib.sha256(
                    (RIS / round_id / f"{family}.{suffix}").read_bytes()
                ).digest())
        assert entry["round"] == round_id
        assert entry["last_sequence"] == number * 2
        assert entry["round_evidence_sha256"] == digest.hexdigest()
        assert entry["request_tail_sha256"] == load_json(
            RIS / round_id / "ipv6.request.json"
        )["request_sha256"]
        assert entry["session_sha256"] == sha256(CHANGE / "session.json")
        assert entry["acquisition_tail_sha256"] == acquisition[
            number * 2 - 1
        ]["entry_sha256"]
        assert entry["previous_sha256"] == previous
        canonical = json.dumps(
            dict(list(entry.items())[:7]), separators=(",", ":")
        ).encode()
        previous = hashlib.sha256(
            b"RIS-CHECKPOINT-V2\0" + canonical
        ).hexdigest()
        assert entry["entry_sha256"] == previous


@pytest.mark.parametrize("round_id", ROUNDS)
def test_round_decisions_are_exact_installed_gate_outputs(tmp_path, round_id):
    """Each retained round decision is byte-exact from a fresh gate run."""
    regenerated = tmp_path / f"{round_id}.json"
    subprocess.run(
        [
            "/app/bin/ris-evidence-gate",
            "/app/policy/visibility.conf",
            str(RIS / round_id / "ipv4.json"),
            str(RIS / round_id / "ipv6.json"),
            str(regenerated),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    retained = DECISIONS / f"{round_id}.json"
    assert retained.read_bytes() == regenerated.read_bytes()
    decision = load_json(retained)
    assert list(decision) == [
        "change_id",
        "decision",
        "selected_profile",
        "reason",
        "query_times",
        "visibility",
    ]
    assert list(decision["query_times"]) == ["ipv4", "ipv6"]
    assert list(decision["visibility"]) == ["ipv4", "ipv6"]
    for family in FAMILIES:
        assert list(decision["visibility"][family]) == ["seeing", "total"]


def test_gate_execution_ledger_is_exact_and_hash_chained():
    """The second chain authenticates exact silent successful gate invocations."""
    raw = (CHANGE / "gate-executions.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode().splitlines()
    assert len(lines) == 3
    previous = "0" * 64
    empty = hashlib.sha256(b"").hexdigest()
    for sequence, (round_id, line) in enumerate(
        zip(ROUNDS, lines, strict=True), start=1
    ):
        entry = json.loads(line, object_pairs_hook=dict)
        assert list(entry) == [
            "sequence", "round", "command", "exit_code", "stdout_sha256",
            "stderr_sha256", "decision_sha256", "policy_sha256",
            "checkpoint_sha256", "previous_sha256",
            "entry_sha256",
        ]
        assert entry == {
            "sequence": sequence,
            "round": round_id,
            "command": [
                "/app/bin/ris-evidence-gate",
                "/app/policy/visibility.conf",
                f"/app/change/ris/{round_id}/ipv4.json",
                f"/app/change/ris/{round_id}/ipv6.json",
                f"/app/change/decisions/{round_id}.json",
            ],
            "exit_code": 0,
            "stdout_sha256": empty,
            "stderr_sha256": empty,
            "decision_sha256": sha256(DECISIONS / f"{round_id}.json"),
            "policy_sha256": sha256(APP / "policy/visibility.conf"),
            "checkpoint_sha256": hashlib.sha256(
                (
                    (CHANGE / "acquisition-checkpoints.jsonl")
                    .read_text().splitlines()[sequence - 1] + "\n"
                ).encode()
            ).hexdigest(),
            "previous_sha256": previous,
            "entry_sha256": entry["entry_sha256"],
        }
        canonical = json.dumps(
            dict(list(entry.items())[:10]), separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        previous = hashlib.sha256(
            b"RIS-GATE-AUDIT-V2\0" + canonical
        ).hexdigest()
        assert entry["entry_sha256"] == previous
        assert line == json.dumps(entry, separators=(",", ":"), ensure_ascii=False)


def test_consensus_is_ordered_authenticated_and_fail_closed():
    """Consensus is derived from all three well-formed round decisions."""
    decision = load_json(CHANGE / "decision.json")
    assert list(decision) == [
        "change_id",
        "decision",
        "selected_profile",
        "reason",
        "rounds",
        "evidence_chain_sha256",
        "gate_chain_sha256",
    ]
    assert decision["change_id"] == "CHG-RIS-EDGE-042"
    assert list(decision["rounds"]) == list(ROUNDS)
    round_values = []
    for round_id in ROUNDS:
        retained = DECISIONS / f"{round_id}.json"
        source = load_json(retained)
        assert list(decision["rounds"][round_id]) == ["decision", "sha256"]
        assert decision["rounds"][round_id] == {
            "decision": source["decision"],
            "sha256": sha256(retained),
        }
        round_values.append(source["decision"])
    assert decision["evidence_chain_sha256"] == sha256(
        CHANGE / "acquisition.jsonl"
    )
    assert decision["gate_chain_sha256"] == sha256(
        CHANGE / "gate-executions.jsonl"
    )
    if round_values == ["APPLY_STANDBY"] * 3:
        assert decision["decision"] == "APPLY_STANDBY"
        assert decision["selected_profile"] == "transit-b-maintenance"
        assert decision["reason"] == "unanimous_apply"
    else:
        assert "HOLD" in round_values
        assert decision["decision"] == "HOLD"
        assert decision["selected_profile"] is None
        assert decision["reason"] == "round_hold"


def test_quorum_attestation_independently_reproduces_consensus():
    """The vote tally independently authenticates the fail-closed outcome."""
    quorum = load_json(CHANGE / "quorum.json")
    assert list(quorum) == [
        "change_id", "votes", "apply_count", "hold_count", "outcome",
        "decision_sha256", "gate_chain_sha256", "quorum_sha256",
    ]
    votes = {
        round_id: load_json(DECISIONS / f"{round_id}.json")["decision"]
        for round_id in ROUNDS
    }
    decision = load_json(CHANGE / "decision.json")
    assert quorum["change_id"] == decision["change_id"]
    assert quorum["votes"] == votes
    assert quorum["apply_count"] == sum(
        value == "APPLY_STANDBY" for value in votes.values()
    )
    assert quorum["hold_count"] == sum(
        value == "HOLD" for value in votes.values()
    )
    assert quorum["outcome"] == decision["decision"]
    assert quorum["decision_sha256"] == sha256(CHANGE / "decision.json")
    assert quorum["gate_chain_sha256"] == sha256(
        CHANGE / "gate-executions.jsonl"
    )
    canonical = json.dumps(
        dict(list(quorum.items())[:7]), separators=(",", ":")
    ).encode()
    assert quorum["quorum_sha256"] == hashlib.sha256(
        b"RIS-QUORUM-V1\0" + canonical
    ).hexdigest()


def test_staged_configuration_matches_consensus_and_validates(tmp_path):
    """The exact selected candidate passes a fresh offline FRR validation."""
    decision = load_json(CHANGE / "decision.json")
    staged = CHANGE / "frr.conf"
    if decision["decision"] == "APPLY_STANDBY":
        regenerated = []
        for number in (1, 2):
            output = tmp_path / f"rendered-{number}.conf"
            result = subprocess.run(
                [
                    "/app/bin/frr-policy-render",
                    "/app/policy",
                    "/app/etc/frr/running.conf",
                    str(output),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            regenerated.append(output.read_bytes())
        assert regenerated[0] == regenerated[1] == staged.read_bytes()
    else:
        assert staged.read_bytes() == (APP / "etc/frr/running.conf").read_bytes()
    validation = subprocess.run(
        ["vtysh", "-C", "-f", str(staged)],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    expected_log = validation.stdout + validation.stderr
    for number in ("01", "02"):
        assert (CHANGE / f"frr-validate-{number}.log").read_text(
            encoding="utf-8"
        ) == expected_log


def test_render_provenance_authenticates_reproducible_candidate():
    """Rendering provenance binds the selected candidate to tools and sources."""
    provenance = load_json(CHANGE / "render-provenance.json")
    assert list(provenance) == [
        "renderer",
        "renderer_sha256",
        "source_manifest_sha256",
        "baseline_sha256",
        "candidate_sha256",
        "reproducible",
    ]
    assert provenance == {
        "renderer": "/app/bin/frr-policy-render",
        "renderer_sha256": sha256(APP / "bin/frr-policy-render"),
        "source_manifest_sha256": sha256(CHANGE / "source-inputs.sha256"),
        "baseline_sha256": sha256(APP / "etc/frr/running.conf"),
        "candidate_sha256": sha256(CHANGE / "frr.conf"),
        "reproducible": True,
    }


def test_validation_attestation_is_ordered_and_authentic():
    """Validation metadata authenticates the command, candidate, log, and decision."""
    validation = load_json(CHANGE / "validation.json")
    assert list(validation) == [
        "commands",
        "exit_codes",
        "candidate_sha256",
        "logs_sha256",
        "logs_match",
        "decision_sha256",
        "render_provenance_sha256",
        "source_manifest_sha256",
        "candidate_delta_sha256",
        "validator_attestation_sha256",
    ]
    assert validation == {
        "commands": [
            ["vtysh", "-C", "-f", "/app/change/frr.conf"],
            ["vtysh", "-C", "-f", "/app/change/frr.conf"],
        ],
        "exit_codes": [0, 0],
        "candidate_sha256": sha256(CHANGE / "frr.conf"),
        "logs_sha256": [
            sha256(CHANGE / "frr-validate-01.log"),
            sha256(CHANGE / "frr-validate-02.log"),
        ],
        "logs_match": True,
        "decision_sha256": sha256(CHANGE / "decision.json"),
        "render_provenance_sha256": sha256(
            CHANGE / "render-provenance.json"
        ),
        "source_manifest_sha256": sha256(CHANGE / "source-inputs.sha256"),
        "candidate_delta_sha256": sha256(CHANGE / "candidate-delta.json"),
        "validator_attestation_sha256": sha256(
            CHANGE / "validator-attestation.json"
        ),
    }


def test_policy_attestation_authenticates_change_inputs():
    """Policy identity and approval are independently bound before release."""
    attestation = load_json(CHANGE / "policy-attestation.json")
    expected = {
        "change_id": "CHG-RIS-EDGE-042",
        "router": "edge-ams-01",
        "ipv4_resource": "193.0.0.0/21",
        "ipv6_resource": "2001:67c:2e8::/48",
        "expected_origin": 3333,
        "min_visibility_percent": 95,
        "standby_profile": "transit-b-maintenance",
        "approval": "approved",
        "visibility_policy_sha256": sha256(APP / "policy/visibility.conf"),
        "window_policy_sha256": sha256(APP / "policy/maintenance/window.conf"),
    }
    assert list(attestation) == [*expected, "attestation_sha256"]
    assert dict(list(attestation.items())[:-1]) == expected
    assert attestation["attestation_sha256"] == hashlib.sha256(
        b"RIS-POLICY-ATTESTATION-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_transport_ledger_binds_http11_status_and_transfer_identity():
    """HTTP/1.1 status lines and TLS transfer identities form a second chain."""
    lines = (CHANGE / "transport-ledger.jsonl").read_text().splitlines()
    assert len(lines) == 6
    previous = "0" * 64
    for sequence, (round_id, family) in enumerate(
        (
            (round_id, family)
            for round_id in ROUNDS
            for family in FAMILIES
        ),
        start=1,
    ):
        entry = json.loads(lines[sequence - 1], object_pairs_hook=dict)
        assert list(entry) == [
            "sequence", "round", "family", "status_line", "http_date",
            "content_type", "remote_ip", "tls_verified", "request_sha256",
            "headers_sha256", "metadata_sha256", "previous_sha256",
            "entry_sha256",
        ]
        headers_path = RIS / round_id / f"{family}.headers"
        metadata_path = RIS / round_id / f"{family}.meta.json"
        request_path = RIS / round_id / f"{family}.request.json"
        raw = headers_path.read_bytes()
        headers = parse_headers(headers_path)
        metadata = load_json(metadata_path)
        expected = {
            "sequence": sequence,
            "round": round_id,
            "family": family,
            "status_line": raw.splitlines()[0].decode("ascii"),
            "http_date": headers["Date"],
            "content_type": headers["Content-Type"],
            "remote_ip": metadata["remote_ip"],
            "tls_verified": True,
            "request_sha256": load_json(request_path)["request_sha256"],
            "headers_sha256": sha256(headers_path),
            "metadata_sha256": sha256(metadata_path),
            "previous_sha256": previous,
        }
        assert re.fullmatch(r"HTTP/1\.1 2\d\d .+", expected["status_line"])
        assert dict(list(entry.items())[:-1]) == expected
        previous = hashlib.sha256(
            b"RIS-TRANSPORT-V1\0"
            + json.dumps(expected, separators=(",", ":")).encode()
        ).hexdigest()
        assert entry["entry_sha256"] == previous
        assert lines[sequence - 1] == json.dumps(entry, separators=(",", ":"))


def test_round_manifests_close_evidence_decision_and_gate_layers():
    """Each round manifest binds eight captures, its decision, and audit tails."""
    lines = (CHANGE / "round-manifests.jsonl").read_text().splitlines()
    checkpoints = [
        json.loads(line)
        for line in (CHANGE / "acquisition-checkpoints.jsonl").read_text().splitlines()
    ]
    gates = [
        json.loads(line)
        for line in (CHANGE / "gate-executions.jsonl").read_text().splitlines()
    ]
    assert len(lines) == 3
    previous = "0" * 64
    for position, round_id in enumerate(ROUNDS):
        entry = json.loads(lines[position], object_pairs_hook=dict)
        artifacts = []
        for family in FAMILIES:
            for suffix in ("request.json", "headers", "json", "meta.json"):
                path = RIS / round_id / f"{family}.{suffix}"
                artifacts.append({
                    "path": str(path),
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                })
        expected = {
            "round": round_id,
            "artifacts": artifacts,
            "decision_sha256": sha256(DECISIONS / f"{round_id}.json"),
            "checkpoint_entry_sha256": checkpoints[position]["entry_sha256"],
            "gate_entry_sha256": gates[position]["entry_sha256"],
            "previous_sha256": previous,
        }
        assert list(entry) == [*expected, "entry_sha256"]
        assert dict(list(entry.items())[:-1]) == expected
        previous = hashlib.sha256(
            b"RIS-ROUND-MANIFEST-V1\0"
            + json.dumps(expected, separators=(",", ":")).encode()
        ).hexdigest()
        assert entry["entry_sha256"] == previous


def test_rollback_validation_proves_recovery_configuration_is_parseable():
    """Two matching offline checks bind the exact rollback and validator."""
    attestation = load_json(CHANGE / "rollback-validation.json")
    expected = {
        "commands": [
            ["vtysh", "-C", "-f", "/app/change/rollback.conf"],
            ["vtysh", "-C", "-f", "/app/change/rollback.conf"],
        ],
        "exit_codes": [0, 0],
        "rollback_sha256": sha256(CHANGE / "rollback.conf"),
        "baseline_sha256": sha256(APP / "etc/frr/running.conf"),
        "logs_sha256": [
            sha256(CHANGE / "rollback-validate-01.log"),
            sha256(CHANGE / "rollback-validate-02.log"),
        ],
        "logs_match": True,
        "validator_attestation_sha256": sha256(
            CHANGE / "validator-attestation.json"
        ),
    }
    assert list(attestation) == [*expected, "attestation_sha256"]
    assert dict(list(attestation.items())[:-1]) == expected
    assert (
        (CHANGE / "rollback-validate-01.log").read_bytes()
        == (CHANGE / "rollback-validate-02.log").read_bytes()
    )
    assert attestation["attestation_sha256"] == hashlib.sha256(
        b"RIS-ROLLBACK-VALIDATION-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_artifact_graph_authenticates_declared_dependency_edges():
    """The dependency graph binds exact node bytes and the required DAG."""
    graph = load_json(CHANGE / "artifact-graph.json")
    names = [
        "acquisition-summary.json",
        "consensus-certificate.json",
        "policy-attestation.json",
        "round-manifests.jsonl",
        "render-provenance.json",
        "rollback-validation.json",
        "validation.json",
    ]
    expected = {
        "nodes": [
            {"name": name, "sha256": sha256(CHANGE / name)}
            for name in names
        ],
        "edges": [
            {"from": "acquisition-summary.json", "to": "round-manifests.jsonl"},
            {"from": "round-manifests.jsonl", "to": "consensus-certificate.json"},
            {"from": "policy-attestation.json", "to": "render-provenance.json"},
            {"from": "consensus-certificate.json", "to": "validation.json"},
            {"from": "render-provenance.json", "to": "validation.json"},
            {"from": "rollback-validation.json", "to": "validation.json"},
        ],
    }
    assert list(graph) == ["nodes", "edges", "graph_sha256"]
    assert dict(list(graph.items())[:-1]) == expected
    assert graph["graph_sha256"] == hashlib.sha256(
        b"RIS-ARTIFACT-GRAPH-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_custody_chain_orders_all_operational_state_transitions():
    """The custody ledger makes every evidence-to-recovery transition explicit."""
    sources = [
        ("acquired", "acquisition-summary.json"),
        ("transport_authenticated", "transport-ledger.jsonl"),
        ("rounds_closed", "round-manifests.jsonl"),
        ("decided", "consensus-certificate.json"),
        ("staged", "render-provenance.json"),
        ("candidate_validated", "validation.json"),
        ("rollback_validated", "rollback-validation.json"),
        ("graph_closed", "artifact-graph.json"),
    ]
    lines = (CHANGE / "custody.jsonl").read_text().splitlines()
    assert len(lines) == len(sources)
    previous = "0" * 64
    for sequence, (line, (stage, name)) in enumerate(
        zip(lines, sources, strict=True), start=1
    ):
        entry = json.loads(line, object_pairs_hook=dict)
        expected = {
            "sequence": sequence,
            "stage": stage,
            "artifact": f"/app/change/{name}",
            "artifact_sha256": sha256(CHANGE / name),
            "previous_sha256": previous,
        }
        assert list(entry) == [*expected, "entry_sha256"]
        assert dict(list(entry.items())[:-1]) == expected
        previous = hashlib.sha256(
            b"RIS-CUSTODY-V1\0"
            + json.dumps(expected, separators=(",", ":")).encode()
        ).hexdigest()
        assert entry["entry_sha256"] == previous


def test_release_authorization_cross_binds_all_new_assurance_layers():
    """Release authorization binds identity, outcome, and every assurance tail."""
    authorization = load_json(CHANGE / "release-authorization.json")
    decision = load_json(CHANGE / "decision.json")
    round_tail = json.loads(
        (CHANGE / "round-manifests.jsonl").read_text().splitlines()[-1]
    )["entry_sha256"]
    custody_tail = json.loads(
        (CHANGE / "custody.jsonl").read_text().splitlines()[-1]
    )["entry_sha256"]
    expected = {
        "change_id": "CHG-RIS-EDGE-042",
        "router": "edge-ams-01",
        "decision": decision["decision"],
        "selected_profile": decision["selected_profile"],
        "policy_attestation_sha256": sha256(CHANGE / "policy-attestation.json"),
        "transport_ledger_sha256": sha256(CHANGE / "transport-ledger.jsonl"),
        "round_manifest_tail_sha256": round_tail,
        "rollback_validation_sha256": sha256(
            CHANGE / "rollback-validation.json"
        ),
        "artifact_graph_sha256": sha256(CHANGE / "artifact-graph.json"),
        "custody_tail_sha256": custody_tail,
        "consensus_certificate_sha256": sha256(
            CHANGE / "consensus-certificate.json"
        ),
        "validation_sha256": sha256(CHANGE / "validation.json"),
    }
    assert list(authorization) == [*expected, "authorization_sha256"]
    assert dict(list(authorization.items())[:-1]) == expected
    assert authorization["authorization_sha256"] == hashlib.sha256(
        b"RIS-RELEASE-AUTHORIZATION-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_capture_binding_chain_uses_length_framed_exact_artifacts():
    """A second domain-separated chain authenticates unambiguous capture frames."""
    lines = (CHANGE / "capture-bindings.jsonl").read_text().splitlines()
    assert len(lines) == 6
    previous = "0" * 64
    position = 0
    for round_id in ROUNDS:
        for family in FAMILIES:
            position += 1
            entry = json.loads(lines[position - 1], object_pairs_hook=dict)
            assert list(entry) == [
                "sequence", "request_sha256", "headers_sha256", "body_sha256",
                "metadata_sha256", "frame_sha256", "previous_sha256",
                "entry_sha256",
            ]
            paths = [
                RIS / round_id / f"{family}.request.json",
                RIS / round_id / f"{family}.headers",
                RIS / round_id / f"{family}.json",
                RIS / round_id / f"{family}.meta.json",
            ]
            raw = [path.read_bytes() for path in paths]
            frame = hashlib.sha256(b"RIS-CAPTURE-FRAME-V1\0")
            for value in raw:
                frame.update(struct.pack(">Q", len(value)))
                frame.update(value)
            assert entry == {
                "sequence": position,
                "request_sha256": load_json(paths[0])["request_sha256"],
                "headers_sha256": sha256(paths[1]),
                "body_sha256": sha256(paths[2]),
                "metadata_sha256": sha256(paths[3]),
                "frame_sha256": frame.hexdigest(),
                "previous_sha256": previous,
                "entry_sha256": entry["entry_sha256"],
            }
            previous = hashlib.sha256(
                b"RIS-CAPTURE-CHAIN-V1\0"
                + json.dumps(
                    dict(list(entry.items())[:7]), separators=(",", ":")
                ).encode()
            ).hexdigest()
            assert entry["entry_sha256"] == previous
            assert lines[position - 1] == json.dumps(entry, separators=(",", ":"))


def test_acquisition_summary_cross_authenticates_all_chain_tails():
    """The summary maps every sequence and closes all acquisition chains."""
    summary = load_json(CHANGE / "acquisition-summary.json")
    assert list(summary) == [
        "acquisition_id", "session_sha256", "sequences",
        "request_tail_sha256", "acquisition_tail_sha256",
        "capture_tail_sha256", "checkpoint_tail_sha256", "summary_sha256",
    ]
    acquisition = [
        json.loads(line)
        for line in (CHANGE / "acquisition.jsonl").read_text().splitlines()
    ]
    captures = [
        json.loads(line)
        for line in (CHANGE / "capture-bindings.jsonl").read_text().splitlines()
    ]
    expected = []
    position = 0
    for round_id in ROUNDS:
        for family in FAMILIES:
            position += 1
            expected.append({
                "sequence": position,
                "round": round_id,
                "family": family,
                "request_sha256": load_json(
                    RIS / round_id / f"{family}.request.json"
                )["request_sha256"],
                "acquisition_entry_sha256": acquisition[position - 1]["entry_sha256"],
                "capture_entry_sha256": captures[position - 1]["entry_sha256"],
            })
    checkpoints = [
        json.loads(line)
        for line in (CHANGE / "acquisition-checkpoints.jsonl").read_text().splitlines()
    ]
    assert summary["acquisition_id"] == load_json(CHANGE / "session.json")["acquisition_id"]
    assert summary["session_sha256"] == sha256(CHANGE / "session.json")
    assert summary["sequences"] == expected
    assert summary["request_tail_sha256"] == expected[-1]["request_sha256"]
    assert summary["acquisition_tail_sha256"] == acquisition[-1]["entry_sha256"]
    assert summary["capture_tail_sha256"] == captures[-1]["entry_sha256"]
    assert summary["checkpoint_tail_sha256"] == checkpoints[-1]["entry_sha256"]
    canonical = json.dumps(
        dict(list(summary.items())[:7]), separators=(",", ":")
    ).encode()
    assert summary["summary_sha256"] == hashlib.sha256(
        b"RIS-ACQUISITION-SUMMARY-V1\0" + canonical
    ).hexdigest()


def test_consensus_certificate_binds_every_decision_input_chain():
    """The outcome certificate cross-authenticates consensus and evidence."""
    certificate = load_json(CHANGE / "consensus-certificate.json")
    assert list(certificate) == [
        "change_id", "outcome", "decision_sha256", "quorum_sha256",
        "acquisition_summary_sha256", "checkpoint_chain_sha256",
        "gate_chain_sha256", "certificate_sha256",
    ]
    decision = load_json(CHANGE / "decision.json")
    assert certificate == {
        "change_id": decision["change_id"],
        "outcome": decision["decision"],
        "decision_sha256": sha256(CHANGE / "decision.json"),
        "quorum_sha256": sha256(CHANGE / "quorum.json"),
        "acquisition_summary_sha256": sha256(
            CHANGE / "acquisition-summary.json"
        ),
        "checkpoint_chain_sha256": sha256(
            CHANGE / "acquisition-checkpoints.jsonl"
        ),
        "gate_chain_sha256": sha256(CHANGE / "gate-executions.jsonl"),
        "certificate_sha256": certificate["certificate_sha256"],
    }
    canonical = json.dumps(
        dict(list(certificate.items())[:7]), separators=(",", ":")
    ).encode()
    assert certificate["certificate_sha256"] == hashlib.sha256(
        b"RIS-CONSENSUS-CERT-V1\0" + canonical
    ).hexdigest()


def test_candidate_delta_replays_exact_unified_diff():
    """The staged delta binds a reproducible patch and exact content counts."""
    result = subprocess.run(
        [
            "diff", "-u", "--label", "/app/etc/frr/running.conf",
            "--label", "/app/change/frr.conf",
            "/app/etc/frr/running.conf", "/app/change/frr.conf",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}
    assert (CHANGE / "candidate.patch").read_bytes() == result.stdout
    delta = load_json(CHANGE / "candidate-delta.json")
    assert list(delta) == [
        "baseline_sha256", "candidate_sha256", "patch_sha256",
        "added_lines", "removed_lines", "delta_sha256",
    ]
    lines = result.stdout.splitlines()
    expected = {
        "baseline_sha256": sha256(APP / "etc/frr/running.conf"),
        "candidate_sha256": sha256(CHANGE / "frr.conf"),
        "patch_sha256": sha256(CHANGE / "candidate.patch"),
        "added_lines": sum(
            line.startswith(b"+") and not line.startswith(b"+++") for line in lines
        ),
        "removed_lines": sum(
            line.startswith(b"-") and not line.startswith(b"---") for line in lines
        ),
    }
    assert dict(list(delta.items())[:5]) == expected
    assert delta["delta_sha256"] == hashlib.sha256(
        b"RIS-CANDIDATE-DELTA-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_validator_attestation_binds_binary_and_version_output():
    """Validator identity is reproducible independently of validation logs."""
    attestation = load_json(CHANGE / "validator-attestation.json")
    assert list(attestation) == [
        "command", "resolved_path", "binary_sha256",
        "version_command", "version_output_sha256", "attestation_sha256",
    ]
    resolved = Path(subprocess.check_output(
        ["realpath", subprocess.check_output(
            ["sh", "-c", "command -v vtysh"], text=True
        ).strip()],
        text=True,
    ).strip())
    version_command = ["dpkg-query", "-W", "-f=${Version}\\n", "frr"]
    version = subprocess.run(
        version_command, stdout=subprocess.PIPE, check=True,
    ).stdout
    expected = {
        "command": "vtysh",
        "resolved_path": str(resolved),
        "binary_sha256": sha256(resolved),
        "version_command": version_command,
        "version_output_sha256": hashlib.sha256(version).hexdigest(),
    }
    assert dict(list(attestation.items())[:5]) == expected
    assert attestation["attestation_sha256"] == hashlib.sha256(
        b"RIS-VALIDATOR-V1\0"
        + json.dumps(expected, separators=(",", ":")).encode()
    ).hexdigest()


def test_source_manifest_authenticates_every_protected_input():
    """The source manifest exactly covers all protected renderer inputs."""
    expected = sorted(
        [
            *(APP / "bin").iterdir(),
            *(APP / "docs").iterdir(),
            *(APP / "etc/frr").iterdir(),
            *(APP / "policy").rglob("*"),
            *(APP / "inventory").iterdir(),
            *(APP / "runbooks").iterdir(),
        ],
        key=str,
    )
    expected = [path for path in expected if path.is_file()]
    entries = parse_manifest(CHANGE / "source-inputs.sha256")
    assert [path for _, path in entries] == expected
    assert len(entries) == 30
    for digest, path in entries:
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and not path.is_symlink()
        assert info.st_nlink == 1
        assert digest == sha256(path)


def test_bundle_index_and_domain_separated_merkle_tree_authenticate_payload():
    """The index and all Merkle levels authenticate the exact payload set."""
    index_path = CHANGE / "bundle-index.json"
    excluded = {
        index_path,
        CHANGE / "bundle-merkle.json",
        CHANGE / "bundle-proofs.json",
        CHANGE / "signing-public.pem",
        CHANGE / "signing-key.json",
        CHANGE / "receipt.sha256",
        CHANGE / "receipt.sig",
        CHANGE / "commit.json",
    }
    expected_index_paths = sorted(
        path for path in ALL_FILES if path not in excluded
    )
    index = load_json(index_path)
    assert [Path(item["path"]) for item in index] == expected_index_paths
    for item, path in zip(index, expected_index_paths, strict=True):
        assert list(item) == ["path", "sha256", "bytes"]
        assert item == {
            "path": str(path),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    leaves = [
        hashlib.sha256(
            b"\x00" + item["path"].encode() + b"\x00"
            + bytes.fromhex(item["sha256"]) + struct.pack(">Q", item["bytes"])
        ).hexdigest()
        for item in index
    ]
    expected_levels = [leaves]
    while len(expected_levels[-1]) > 1:
        current = expected_levels[-1]
        if len(current) % 2:
            current = [*current, current[-1]]
        expected_levels.append([
            hashlib.sha256(
                b"\x01" + bytes.fromhex(current[pos])
                + bytes.fromhex(current[pos + 1])
            ).hexdigest()
            for pos in range(0, len(current), 2)
        ])
    merkle = load_json(CHANGE / "bundle-merkle.json")
    assert list(merkle) == [
        "algorithm", "leaf_count", "levels", "root_sha256"
    ]
    assert merkle == {
        "algorithm": "sha256-domain-separated-v1",
        "leaf_count": len(index),
        "levels": expected_levels,
        "root_sha256": expected_levels[-1][0],
    }


def test_critical_payload_merkle_proofs_replay_to_retained_root():
    """Compact inclusion paths authenticate four operationally critical files."""
    proofs = load_json(CHANGE / "bundle-proofs.json")
    expected_paths = [
        "/app/change/decision.json",
        "/app/change/frr.conf",
        "/app/change/source-inputs.sha256",
        "/app/change/validation.json",
    ]
    assert list(proofs) == expected_paths
    index = load_json(CHANGE / "bundle-index.json")
    merkle = load_json(CHANGE / "bundle-merkle.json")
    for path_text, proof in proofs.items():
        assert list(proof) == ["index", "leaf_sha256", "siblings"]
        item = index[proof["index"]]
        assert item["path"] == path_text
        leaf = hashlib.sha256(
            b"\x00" + path_text.encode() + b"\x00"
            + bytes.fromhex(item["sha256"])
            + struct.pack(">Q", item["bytes"])
        ).hexdigest()
        assert proof["leaf_sha256"] == leaf
        current = bytes.fromhex(leaf)
        for sibling in proof["siblings"]:
            assert list(sibling) == ["side", "sha256"]
            other = bytes.fromhex(sibling["sha256"])
            assert sibling["side"] in {"left", "right"}
            left, right = (
                (other, current) if sibling["side"] == "left"
                else (current, other)
            )
            current = hashlib.sha256(b"\x01" + left + right).digest()
        assert current.hex() == merkle["root_sha256"]


def test_signing_key_attestation_binds_pem_and_der_identity():
    """The key attestation pins Ed25519 type plus PEM and DER fingerprints."""
    attestation = load_json(CHANGE / "signing-key.json")
    assert list(attestation) == [
        "algorithm", "public_key_sha256", "public_key_der_sha256",
        "signature_target",
    ]
    assert attestation["algorithm"] == "Ed25519"
    assert attestation["public_key_sha256"] == sha256(
        CHANGE / "signing-public.pem"
    )
    result = subprocess.run(
        [
            "openssl", "pkey", "-pubin",
            "-in", str(CHANGE / "signing-public.pem"), "-outform", "DER",
        ],
        check=True,
        capture_output=True,
    )
    assert attestation["public_key_der_sha256"] == hashlib.sha256(
        result.stdout
    ).hexdigest()
    assert attestation["signature_target"] == "/app/change/receipt.sha256"


def test_signed_receipt_and_final_commit_bind_every_layer():
    """A fresh Ed25519 signature and final commit close the bundle hierarchy."""
    entries = parse_manifest(CHANGE / "receipt.sha256")
    expected_receipt_paths = sorted(
        path for path in ALL_FILES
        if path not in {
            CHANGE / "receipt.sha256",
            CHANGE / "receipt.sig",
            CHANGE / "commit.json",
        }
    )
    assert [path for _, path in entries] == expected_receipt_paths
    for digest, path in entries:
        assert digest == sha256(path)
    verification = subprocess.run(
        [
            "openssl", "pkeyutl", "-verify", "-rawin", "-pubin",
            "-inkey", str(CHANGE / "signing-public.pem"),
            "-in", str(CHANGE / "receipt.sha256"),
            "-sigfile", str(CHANGE / "receipt.sig"),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert verification.returncode == 0, verification.stderr
    public = subprocess.run(
        [
            "openssl", "pkey", "-pubin",
            "-in", str(CHANGE / "signing-public.pem"), "-text", "-noout",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ED25519" in public.stdout.upper()
    commit = load_json(CHANGE / "commit.json")
    assert list(commit) == [
        "acquisition_id", "payload_count", "merkle_root_sha256",
        "bundle_index_sha256", "bundle_proofs_sha256", "receipt_sha256",
        "signature_sha256", "public_key_sha256", "signing_key_sha256",
        "completed_at", "commit_sha256",
    ]
    metadata = load_json(RIS / "01/ipv4.meta.json")
    index = load_json(CHANGE / "bundle-index.json")
    merkle = load_json(CHANGE / "bundle-merkle.json")
    assert commit["acquisition_id"] == metadata["acquisition_id"]
    assert commit["payload_count"] == len(index)
    assert commit["merkle_root_sha256"] == merkle["root_sha256"]
    for key, name in (
        ("bundle_index_sha256", "bundle-index.json"),
        ("bundle_proofs_sha256", "bundle-proofs.json"),
        ("receipt_sha256", "receipt.sha256"),
        ("signature_sha256", "receipt.sig"),
        ("public_key_sha256", "signing-public.pem"),
        ("signing_key_sha256", "signing-key.json"),
    ):
        assert commit[key] == sha256(CHANGE / name)
    completed = datetime.strptime(
        commit["completed_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    for round_id in ROUNDS:
        for family in FAMILIES:
            transfer_completed = datetime.strptime(
                load_json(RIS / round_id / f"{family}.meta.json")["completed_at"],
                "%Y-%m-%dT%H:%M:%S.%fZ",
            ).replace(tzinfo=timezone.utc)
            assert completed >= transfer_completed
    canonical = json.dumps(
        dict(list(commit.items())[:10]), separators=(",", ":")
    ).encode()
    assert commit["commit_sha256"] == hashlib.sha256(
        b"RIS-COMMIT-V1\0" + canonical
    ).hexdigest()
