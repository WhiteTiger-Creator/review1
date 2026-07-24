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
    CHANGE / "acquisition.jsonl",
    CHANGE / "bundle-index.json",
    CHANGE / "bundle-merkle.json",
    CHANGE / "bundle-proofs.json",
    CHANGE / "commit.json",
    CHANGE / "decision.json",
    CHANGE / "frr-validate-01.log",
    CHANGE / "frr-validate-02.log",
    CHANGE / "frr.conf",
    CHANGE / "gate-executions.jsonl",
    CHANGE / "render-provenance.json",
    CHANGE / "rollback.conf",
    CHANGE / "quorum.json",
    CHANGE / "session.json",
    CHANGE / "signing-key.json",
    CHANGE / "source-inputs.sha256",
    CHANGE / "signing-public.pem",
    CHANGE / "validation.json",
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
    """Every retained body and final header block has coherent RIPE data."""
    payload = load_json(RIS / round_id / f"{family}.json")
    headers = parse_headers(RIS / round_id / f"{family}.headers")
    fetched_at = email.utils.parsedate_to_datetime(headers["Date"]).astimezone(
        timezone.utc
    )
    query_time = datetime.fromisoformat(
        payload["data"]["query_time"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    assert query_time <= fetched_at
    assert (fetched_at - query_time).total_seconds() <= 12 * 60 * 60
    assert payload["status"] == "ok"
    assert payload["data"]["resource"] == resource
    assert isinstance(payload["data"]["origins"], list)
    assert isinstance(payload["data"]["more_specifics"], list)
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
            assert metadata["http_version"] in {"1.1", "2", "3"}
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
                "url", "user_agent", "previous_request_sha256",
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
                "previous_request_sha256": previous,
                "request_sha256": request["request_sha256"],
            }
            canonical = json.dumps(
                dict(list(request.items())[:8]), separators=(",", ":")
            ).encode()
            previous = hashlib.sha256(
                b"RIS-REQUEST-V1\0" + canonical
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
        assert entry["acquisition_tail_sha256"] == acquisition[
            number * 2 - 1
        ]["entry_sha256"]
        assert entry["previous_sha256"] == previous
        canonical = json.dumps(
            dict(list(entry.items())[:5]), separators=(",", ":")
        ).encode()
        previous = hashlib.sha256(
            b"RIS-CHECKPOINT-V1\0" + canonical
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
            "stderr_sha256", "decision_sha256", "previous_sha256",
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
            "previous_sha256": previous,
            "entry_sha256": entry["entry_sha256"],
        }
        canonical = json.dumps(
            dict(list(entry.items())[:8]), separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        previous = hashlib.sha256(
            b"RIS-GATE-AUDIT-V1\0" + canonical
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
    }


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
