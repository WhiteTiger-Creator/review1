import json
import re
import shutil
import subprocess
from pathlib import Path

ENV_DIR = Path("/app/environment")
OUT_DIR = Path("/app/output")
TRACE_PATH = OUT_DIR / "risk_trace.json"
NOTE_PATH = OUT_DIR / "residual_risk.md"
REVISION_DIR = ENV_DIR / "local"
REVISION_PATH = REVISION_DIR / "rev_b.json"
SPLIT_PATH = REVISION_DIR / "holdout_map.json"
EVENTS_PATH = REVISION_DIR / "events_b.jsonl"
CHECKPOINT_PATH = REVISION_DIR / "checkpoint.json"
ALIASES_PATH = REVISION_DIR / "alias_map.json"
ALIAS_SCOPES_PATH = REVISION_DIR / "alias_scopes.json"
AUTHORITY_PATH = REVISION_DIR / "authority_overrides.json"
CATALOG_PATH = REVISION_DIR / "catalog.tsv"
MANIFEST_PATH = REVISION_DIR / "replay_manifest.json"


def run_tool():
    """The normal generator must rebuild the public packet from local state."""
    if OUT_DIR.exists():
        for path in OUT_DIR.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            "/app/environment/Cargo.toml",
            "--",
            "--out",
            "/app/output",
        ],
        check=False,
        cwd=ENV_DIR,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert TRACE_PATH.exists(), "missing risk_trace.json"
    assert NOTE_PATH.exists(), "missing residual_risk.md"
    return json.loads(TRACE_PATH.read_text()), NOTE_PATH.read_text()


def load_json(path):
    return json.loads(path.read_text())


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def manifest():
    return load_json(MANIFEST_PATH)


def split_book():
    return load_json(SPLIT_PATH)


def active_revision_path():
    return REVISION_DIR / f"{manifest()['active_revision']}.json"


def selected_event_key(row):
    ranks = manifest()["generation_rank"]
    return (
        ranks[row["generation"]],
        row["replay_seq"],
        row["observed_at"],
        row["evidence_id"],
    )


def disallowed_events():
    replay = manifest()
    suppressed = set(replay["suppressed_evidence_ids"])
    return [
        row
        for row in load_jsonl(EVENTS_PATH)
        if row["evidence_id"] in suppressed or row["observed_at"] > replay["closed_at"]
    ]


def latest_events_by_id():
    """Replay rows collapse only after suppression and close-window filtering."""
    replay = manifest()
    suppressed = set(replay["suppressed_evidence_ids"])
    latest = {}
    for row in load_jsonl(EVENTS_PATH):
        if row["evidence_id"] in suppressed:
            continue
        if row["observed_at"] > replay["closed_at"]:
            continue
        prior = latest.get(row["id"])
        if prior is None or selected_event_key(row) > selected_event_key(prior):
            latest[row["id"]] = row
    return latest


def review_rows():
    split = split_book()
    latest = latest_events_by_id()
    return split, [latest[item] for item in split["review"]]


def aliases():
    return load_json(ALIASES_PATH)


def alias_scopes():
    return load_json(ALIAS_SCOPES_PATH)


def scoped_alias(kind, value, generation):
    book = aliases()
    scopes = alias_scopes()
    table_name = f"{kind}_aliases"
    scope_name = f"{kind}_scopes"
    canonical = book[table_name].get(value)
    if canonical is None:
        return value
    minimum = scopes["minimum_confidence"]
    for row in scopes[scope_name]:
        if (
            row["alias"] == value
            and row["canonical"] == canonical
            and generation in row["valid_generations"]
            and row["confidence"] >= minimum
        ):
            return canonical
    return value


def canonical_pair(row):
    principal = scoped_alias("principal", row["principal"], row["generation"])
    claim = scoped_alias("claim", row["claim"], row["generation"])
    return principal, claim


def rule_index():
    revision = load_json(active_revision_path())
    return revision, {(row["principal"], row["claim"]): row for row in revision["rows"]}


def final_policy_for_event(event):
    _revision, rules = rule_index()
    overrides = load_json(AUTHORITY_PATH)
    principal, claim = canonical_pair(event)
    rule = rules.get((principal, claim), overrides["default_if_unmatched"])
    policy = {
        "authority_source": rule["authority_source"],
        "decision": rule["decision"],
        "freshness": rule["freshness"],
        "support": rule["support"],
    }
    for gate in overrides["consent_gates"]:
        if (
            gate["principal"] == principal
            and gate["claim"] == claim
            and event["consent_state"] != gate["required_state"]
        ):
            policy.update(gate["when_not_met"])
    for window in overrides["expiry_windows"]:
        if (
            window["principal"] == principal
            and window["claim"] == claim
            and event["observed_at"] > window["stale_after"]
        ):
            policy.update(window["when_expired"])
    return policy


def is_qualifying_policy(policy):
    return (
        policy["support"] == "unsupported"
        or policy["freshness"] != "fresh"
        or policy["decision"] == "deny"
    )


def checkpoint_index():
    checkpoint = load_json(CHECKPOINT_PATH)
    split = split_book()
    branch = split["checkpoint_branch"]
    max_seq = split["checkpoint_seq"]
    rows = {}
    for row in checkpoint["rows"]:
        if row.get("branch") != branch:
            continue
        if row.get("closed") is not True:
            continue
        if row.get("closed_seq", -1) > max_seq:
            continue
        prior = rows.get(row["id"])
        if prior is None or row["closed_seq"] > prior["closed_seq"]:
            rows[row["id"]] = row
    return checkpoint, rows


def catalog_labels():
    lines = [line for line in CATALOG_PATH.read_text().splitlines() if line.strip()]
    header = lines[0].split("\t")
    selected = {}
    for line in lines[1:]:
        row = dict(zip(header, line.split("\t")))
        if row["owner"] != "procurement" or row["status"] != "active":
            continue
        prior = selected.get(row["id"])
        if prior is None or int(row["sequence"]) > int(prior["sequence"]):
            selected[row["id"]] = row
    return {record_id: row["label"] for record_id, row in selected.items()}


def by_id(trace):
    return {row["id"]: row for row in trace["records"]}


def linked_note_line(note, record_id):
    lines = [line.lower() for line in note.splitlines() if record_id.lower() in line.lower()]
    assert lines, f"missing note line for {record_id}"
    return "\n".join(lines)


def _locally_negated(text, start):
    clause_start = max(
        text.rfind(".", 0, start),
        text.rfind(";", 0, start),
        text.rfind("\n", 0, start),
    )
    prefix = text[clause_start + 1 : start]
    return re.search(
        r"\b("
        r"no|not|never|without|cannot|can not|can't|"
        r"does not|doesn't|do not|don't|is not|isn't|are not|aren't|"
        r"fails to|failed to"
        r")\b",
        prefix,
    )


def assert_no_affirmative_match(text, patterns):
    lower = text.lower()
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            assert _locally_negated(lower, match.start()), (
                f"forbidden affirmative claim present: {match.group(0)}"
            )


def assert_no_false_fresh_authority_claim(text, principal, *, include_generic=False):
    patterns = [
        rf"\bfresh\s+{principal}\s+authority\b",
        rf"\b{principal}\s+authority\s+is\s+fresh\b",
    ]
    if include_generic:
        patterns.append(r"\bfresh\s+authority\b")
    assert_no_affirmative_match(text, patterns)


def assert_no_unsupported_precision_claim(text, principal, *, include_generic=False):
    patterns = [
        rf"\b{principal}\s+authority\s+supports?\s+precise\s+eta\s+certainty\b",
        rf"\b{principal}\s+authority\s+supports?\s+precise\b",
    ]
    if include_generic:
        patterns.append(r"\bfresh\s+authority\s+supports?\s+precise\s+eta\s+certainty\b")
    assert_no_affirmative_match(text, patterns)


def assert_no_packet_wide_precision_claim(text):
    patterns = [
        r"\b(?:review\s+)?packet\s+supports?\s+precise\s+eta\s+certainty\s+across\s+the\s+evaluated\s+principals\b",
        r"\bsupports?\s+precise\s+eta\s+certainty\s+across\s+the\s+evaluated\s+principals\b",
    ]
    assert_no_affirmative_match(text, patterns)


def test_ax():
    """The regenerated JSON keeps the declared packet shape and active revision."""
    trace, note = run_tool()
    revision, _rules = rule_index()
    _split, expected = review_rows()
    assert set(trace) == {
        "runs",
        "records",
        "principal_transitions",
        "holdout_summary",
        "statement_evidence",
    }
    assert len(trace["runs"]) == 1
    run = trace["runs"][0]
    assert isinstance(run["tool"], str) and run["tool"]
    assert run["revision"] == revision["name"] == manifest()["active_revision"]
    assert run["record_count"] == len(expected)
    assert note.startswith("# Residual risk statement")


def test_bx():
    """Replay recovery uses close-window eligibility, suppression, and pinned order."""
    trace, note = run_tool()
    _split, expected = review_rows()
    records = trace["records"]
    assert [row["id"] for row in records] == [row["id"] for row in expected]
    for generated, event in zip(records, expected):
        assert generated["evidence_id"] == event["evidence_id"]
        assert generated["generation"] == event["generation"]
        assert generated["observed_at"] == event["observed_at"]
        assert generated["replay_seq"] == event["replay_seq"]
    trace_json = json.dumps(trace)
    for event in disallowed_events():
        assert event["evidence_id"] not in trace_json
        assert event["evidence_id"] not in note


def test_cx():
    """The pinned split excludes held-out rows from records, evidence, and markdown."""
    trace, note = run_tool()
    split, expected = review_rows()
    review_ids = {row["id"] for row in expected}
    holdout_ids = set(split["holdout"])
    assert set(by_id(trace)) == review_ids
    assert set(by_id(trace)) & holdout_ids == set()
    summary = trace["holdout_summary"]
    assert summary["pinned_split"] == split["pinned"]
    assert summary["review_count"] == len(split["review"])
    assert summary["held_out_count"] == len(split["holdout"])
    assert summary["held_out_records"] == split["holdout"]
    evidence_ids = {line["record_id"] for line in trace["statement_evidence"]}
    assert evidence_ids == review_ids
    for event in load_jsonl(EVENTS_PATH):
        if event["id"] in holdout_ids:
            assert event["id"].lower() not in note.lower()
            assert event["evidence_id"].lower() not in note.lower()


def test_dx():
    """Records reconcile scoped aliases, authority overrides, and closed checkpoint state."""
    trace, _note = run_tool()
    _checkpoint, prior_rows = checkpoint_index()
    _split, events = review_rows()
    generated = by_id(trace)
    for event in events:
        record = generated[event["id"]]
        principal, claim = canonical_pair(event)
        policy = final_policy_for_event(event)
        prior = prior_rows[event["id"]]
        assert record["principal"] == principal
        assert record["claim"] == claim
        assert record["source_principal"] == event["principal"]
        assert record["source_claim"] == event["claim"]
        assert record["authority_source"] == policy["authority_source"]
        assert record["freshness"] == policy["freshness"]
        assert record["uncertainty_support"] == policy["support"]
        assert record["decision"] == policy["decision"]
        assert record["checkpoint_revision"] == prior["revision"]
        assert record["prior_decision"] == prior["decision"]
        assert record["prior_freshness"] == prior["freshness"]
        assert record["prior_support"] == prior["support"]
        changed = (
            prior["evidence_id"] != record["evidence_id"]
            or prior["decision"] != record["decision"]
            or prior["freshness"] != record["freshness"]
            or prior["support"] != record["uncertainty_support"]
        )
        assert record["recovery_action"] == ("changed" if changed else "unchanged")


def test_ex():
    """Principal transitions include only affected reviewed records by canonical principal."""
    trace, _note = run_tool()
    _split, events = review_rows()
    expected = {}
    for event in events:
        principal, _claim = canonical_pair(event)
        policy = final_policy_for_event(event)
        if is_qualifying_policy(policy):
            if principal not in expected:
                expected[principal] = set()
            expected[principal].add(event["id"])
    transition_map = {item["principal"]: item for item in trace["principal_transitions"]}
    assert set(transition_map) == set(expected)
    for principal, ids in expected.items():
        assert set(transition_map[principal]["affected_records"]) == ids
        assert transition_map[principal]["affected_records"]


def test_fx():
    """Statement evidence mirrors active labels and cites each reviewed record."""
    trace, note = run_tool()
    evidence = trace["statement_evidence"]
    records = by_id(trace)
    labels = catalog_labels()
    assert {line["record_id"] for line in evidence} == set(records)
    assert len(evidence) == len(records)
    for line in evidence:
        record = records[line["record_id"]]
        assert line["claim_id"] == labels[line["record_id"]]
        assert line["evidence_id"] == record["evidence_id"]
        assert line["principal"] == record["principal"]
        assert line["support"] == record["uncertainty_support"]
        assert line["freshness"] == record["freshness"]
        assert line["generation"] == record["generation"]
        assert line["recovery_action"] == record["recovery_action"]
        assert isinstance(line["phrase"], str) and line["phrase"]
        assert line["claim_id"] in line["phrase"]
        assert line["record_id"] in line["phrase"]
        assert line["evidence_id"] in line["phrase"]
        linked = linked_note_line(note, line["record_id"])
        assert line["claim_id"].lower() in linked
        assert line["evidence_id"].lower() in linked
        assert line["principal"].lower() in linked
        assert line["freshness"].lower() in linked
        assert line["generation"].lower() in linked
        assert line["recovery_action"].lower() in linked


def test_gx():
    """Markdown separates truthful fresh authority from false ETA certainty claims."""
    _trace, note = run_tool()
    _split, events = review_rows()
    note_lower = note.lower()
    assert "supported uncertainty" in note_lower
    assert "unsupported eta certainty" in note_lower
    assert_no_packet_wide_precision_claim(note)
    fresh_supported_principals = set()
    for event in events:
        principal, _claim = canonical_pair(event)
        policy = final_policy_for_event(event)
        linked = linked_note_line(note, event["id"])
        is_fresh_supported = (
            policy["support"] == "supported"
            and policy["freshness"] == "fresh"
            and policy["decision"] == "allow"
        )
        if is_fresh_supported:
            fresh_supported_principals.add(principal)
            assert "fresh" in linked
            assert "supported" in linked
        else:
            assert policy["freshness"] in linked
            assert_no_false_fresh_authority_claim(linked, principal, include_generic=True)
            assert_no_unsupported_precision_claim(linked, principal, include_generic=True)
    for principal in ("customer", "courier", "merchant"):
        if principal not in fresh_supported_principals:
            assert_no_false_fresh_authority_claim(note, principal)
            assert_no_unsupported_precision_claim(note, principal)


def test_hx():
    """Clean repeated runs are deterministic and write only the declared files."""
    first_trace, first_note = run_tool()
    first_names = sorted(path.name for path in OUT_DIR.glob("*"))
    assert first_names == ["residual_risk.md", "risk_trace.json"]
    first_json = json.dumps(first_trace, sort_keys=True)
    second_trace, second_note = run_tool()
    second_names = sorted(path.name for path in OUT_DIR.glob("*"))
    assert second_names == ["residual_risk.md", "risk_trace.json"]
    assert first_json == json.dumps(second_trace, sort_keys=True)
    assert first_note == second_note
