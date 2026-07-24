import hashlib
import hmac
import json
import os
import subprocess

OUTPUT_PATH = "/app/ledger/output.json"
BINARY_PATH = "/app/binary/tripfix"
FEEDS_DIR = "/app/feeds"


def _load_output():
    with open(OUTPUT_PATH, "r") as fh:
        return json.load(fh)


def _feeds_digest():
    h = hashlib.sha256()
    for name in sorted(os.listdir(FEEDS_DIR)):
        full = os.path.join(FEEDS_DIR, name)
        h.update(name.encode("utf-8"))
        h.update(b"\x00")
        with open(full, "rb") as fh:
            h.update(fh.read())
        h.update(b"\x00")
    return h.hexdigest()


def test_output_file_is_valid_json():
    """Output ledger document at /app/ledger/output.json parses as valid JSON."""
    doc = _load_output()
    assert isinstance(doc, dict)
    for key in ("report_id", "window", "report_digest", "decisions", "totals", "route_share"):
        assert key in doc, f"missing top-level key: {key}"


def test_report_envelope_fields():
    """report_id is tripfix-v1; window spans 2026-06-22T00:00:00Z through 04:00:00Z."""
    doc = _load_output()
    assert doc["report_id"] == "tripfix-v1"
    assert doc["window"]["start"] == "2026-06-22T00:00:00Z"
    assert doc["window"]["end"] == "2026-06-22T04:00:00Z"


def test_decision_count_is_twenty_four():
    """The four feeds plus the quarantine carrier emit exactly 24 decisions in this fixture."""
    doc = _load_output()
    assert len(doc["decisions"]) == 24


def test_decision_ordinals_are_sequential_one_based():
    """Each decision carries a 1-based ordinal matching its emit index."""
    doc = _load_output()
    for i, d in enumerate(doc["decisions"], start=1):
        assert d["ordinal"] == i


def test_decision_sort_order_received_ts_then_trip_then_feed():
    """Decisions sort by received_ts ASC, trip_id ASC, feed ASC; unparseable timestamps trail last."""
    doc = _load_output()
    trip_in_order = [d["trip_id"] for d in doc["decisions"]]
    expected = [
        "T-101", "T-102", "T-103", "T-101", "T-103",
        "T-104", "T-201", "T-202", "T-203", "T-301",
        "T-302", "T-105", "T-106", "T-107", "T-108",
        "T-109", "T-401", "T-402", "Q-001", "T-501",
        "T-502", "T-403", "T-503", "T-504",
    ]
    assert trip_in_order == expected


def test_admitted_scheduled_admits_count_six():
    """Six trips reach ADMITTED_SCHEDULED: T-101, T-103, T-301, T-105, T-106, T-107."""
    doc = _load_output()
    admitted = [d for d in doc["decisions"] if d["verdict"] == "ADMITTED_SCHEDULED"]
    trips = sorted(d["trip_id"] for d in admitted)
    assert trips == ["T-101", "T-103", "T-105", "T-106", "T-107", "T-301"]


def test_skipped_stop_preempts_admit_for_t102():
    """T-102 carries a sub-stop tagged SKIPPED so the trip-level verdict is SKIPPED_STOP, not ADMITTED_SCHEDULED."""
    doc = _load_output()
    t102 = [d for d in doc["decisions"] if d["trip_id"] == "T-102" and d["feed"] == "alpha"]
    assert len(t102) == 1
    assert t102[0]["verdict"] == "SKIPPED_STOP"


def test_dedup_duplicate_pairs_on_trip_plus_start_date():
    """T-101 and T-103 reappear on the beta feed inside the same hour; both reappearances become DEDUP_DUPLICATE because earliest received_ts wins."""
    doc = _load_output()
    dups = [d for d in doc["decisions"] if d["verdict"] == "DEDUP_DUPLICATE"]
    assert len(dups) == 2
    pairs = sorted((d["trip_id"], d["feed"]) for d in dups)
    assert pairs == [("T-101", "beta"), ("T-103", "beta")]


def test_cap_exceeded_t104_hits_route_hour_limit():
    """R-BUS-1 in hour 00 fills three slots (T-101 admit, T-102 skipped, T-103 admit) so T-104 is CAP_EXCEEDED."""
    doc = _load_output()
    t104 = [d for d in doc["decisions"] if d["trip_id"] == "T-104"]
    assert len(t104) == 1
    assert t104[0]["verdict"] == "CAP_EXCEEDED"
    assert t104[0]["route_id"] == "R-BUS-1"


def test_cascade_suppressed_demotes_only_first_cap_in_armed_hour():
    """Hour 00 had two DEDUP_DUPLICATE events, arming hour 01. T-108 is the first CAP candidate in hour 01 and is demoted; T-109 stays CAP_EXCEEDED."""
    doc = _load_output()
    t108 = next(d for d in doc["decisions"] if d["trip_id"] == "T-108")
    t109 = next(d for d in doc["decisions"] if d["trip_id"] == "T-109")
    assert t108["verdict"] == "CASCADE_SUPPRESSED"
    assert t109["verdict"] == "CAP_EXCEEDED"


def test_canceled_trip_preempts_cap_for_t203():
    """T-203 (CANCELED) does not consume a route slot; verdict is CANCELED_TRIP regardless of the hour total."""
    doc = _load_output()
    t203 = next(d for d in doc["decisions"] if d["trip_id"] == "T-203")
    assert t203["verdict"] == "CANCELED_TRIP"
    assert t203["route_id"] == "R-RAPID-1"


def test_sequence_rejected_for_quoted_stop_sequence_t401():
    """T-401 has a stop_sequence quoted as the string two; strict-int rejects it as SEQUENCE_REJECTED with no rescue."""
    doc = _load_output()
    t401 = next(d for d in doc["decisions"] if d["trip_id"] == "T-401")
    assert t401["verdict"] == "SEQUENCE_REJECTED"


def test_pin_rescued_seal_demotes_sequence_rejected_for_t402():
    """T-402 also has a quoted stop_sequence but its (feed,trip_id,received_ts) matches the active seal so its verdict is PIN_RESCUED instead of SEQUENCE_REJECTED. The trailing HMAC recomputation is a self-consistency check on the seal hex baked into envelope_seals.json5, confirming the HMAC8 preimage formula is the documented feed|trip_id|received_ts triple."""
    doc = _load_output()
    t402 = next(d for d in doc["decisions"] if d["trip_id"] == "T-402")
    assert t402["verdict"] == "PIN_RESCUED"
    msg = "beta|T-402|2026-06-22T01:35:00Z"
    expected_seal = hmac.new(b"trip-pin-v1", msg.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    assert expected_seal == "545986f4de50e9bc"


def test_quarantine_feed_forces_sequence_rejected_q001():
    """Records on the unknown_v9 carrier are forced to SEQUENCE_REJECTED and cannot be rescued."""
    doc = _load_output()
    q = next(d for d in doc["decisions"] if d["trip_id"] == "Q-001")
    assert q["verdict"] == "SEQUENCE_REJECTED"
    assert q["feed"] == "quarantine"


def test_timestamp_rejected_for_unparseable_received_ts_t403():
    """T-403 has received_ts set to the literal not-a-time; verdict is TIMESTAMP_REJECTED and it sorts among the trailing TIMESTAMP_REJECTED block."""
    doc = _load_output()
    t403 = next(d for d in doc["decisions"] if d["trip_id"] == "T-403")
    assert t403["verdict"] == "TIMESTAMP_REJECTED"


def test_route_unknown_for_t501_phantom_route():
    """T-501 carries route_id R-PHANTOM-9 which is not in /app/timetable/timetable_routes.tsv; verdict is ROUTE_UNKNOWN and the record never reaches the cap or dedup layers."""
    doc = _load_output()
    t501 = next(d for d in doc["decisions"] if d["trip_id"] == "T-501")
    assert t501["verdict"] == "ROUTE_UNKNOWN"
    assert t501["route_id"] == "R-PHANTOM-9"


def test_stale_ingest_for_t502_over_six_hours_after_received_ts():
    """T-502 ingest_ts is 6h25m after received_ts which exceeds the 21600s stale threshold; verdict is STALE_INGEST."""
    doc = _load_output()
    t502 = next(d for d in doc["decisions"] if d["trip_id"] == "T-502")
    assert t502["verdict"] == "STALE_INGEST"


def test_strict_timestamp_grammar_rejects_fractional_seconds_t503():
    """T-503 received_ts is 2026-06-22T02:30:00.500Z; the strict grammar requires whole-second precision so verdict is TIMESTAMP_REJECTED even though RFC3339 parsers would accept it."""
    doc = _load_output()
    t503 = next(d for d in doc["decisions"] if d["trip_id"] == "T-503")
    assert t503["verdict"] == "TIMESTAMP_REJECTED"


def test_strict_timestamp_grammar_rejects_numeric_offset_t504():
    """T-504 received_ts is 2026-06-22T02:35:00+00:00; only a literal trailing Z is allowed so verdict is TIMESTAMP_REJECTED."""
    doc = _load_output()
    t504 = next(d for d in doc["decisions"] if d["trip_id"] == "T-504")
    assert t504["verdict"] == "TIMESTAMP_REJECTED"


def test_timestamp_rejected_block_trails_in_trip_id_order():
    """All three TIMESTAMP_REJECTED records trail the ledger in trip_id ascending order: T-403, T-503, T-504."""
    doc = _load_output()
    last3 = [d["trip_id"] for d in doc["decisions"][-3:]]
    assert last3 == ["T-403", "T-503", "T-504"]


def test_totals_carry_all_fourteen_verdict_codes_with_exact_counts():
    """Every one of the fourteen closed verdict codes is present in totals, even where the count is zero."""
    doc = _load_output()
    expected = {
        "ADMITTED_SCHEDULED": 6,
        "ADMITTED_ADDED": 1,
        "ADMITTED_NO_DATA": 1,
        "ADMITTED_UNSCHEDULED": 1,
        "CANCELED_TRIP": 1,
        "SKIPPED_STOP": 1,
        "DEDUP_DUPLICATE": 2,
        "CAP_EXCEEDED": 2,
        "CASCADE_SUPPRESSED": 1,
        "SEQUENCE_REJECTED": 2,
        "PIN_RESCUED": 1,
        "TIMESTAMP_REJECTED": 3,
        "ROUTE_UNKNOWN": 1,
        "STALE_INGEST": 1,
    }
    assert doc["totals"] == expected


def test_route_share_lists_every_route_admit_count_only():
    """route_share names every configured route and counts only the four ADMITTED_* verdicts."""
    doc = _load_output()
    expected = {"R-BUS-1": 5, "R-BUS-2": 2, "R-RAPID-1": 2}
    assert doc["route_share"] == expected


def test_idempotent_rerun_produces_identical_bytes():
    """Running the built binary a second time yields the same bytes; the pipeline is deterministic."""
    with open(OUTPUT_PATH, "rb") as fh:
        first = fh.read()
    subprocess.run([BINARY_PATH], check=True)
    with open(OUTPUT_PATH, "rb") as fh:
        second = fh.read()
    assert first == second


def test_input_feeds_remain_unchanged_after_run():
    """The feeds directory must not be mutated by the pipeline; aggregate SHA256 stays constant across runs."""
    before = _feeds_digest()
    subprocess.run([BINARY_PATH], check=True)
    after = _feeds_digest()
    assert before == after


def test_report_digest_matches_canonical_preimage():
    """report_digest is the first 16 hex chars of SHA-256 over the canonical preimage tripfix-v1|N|ord:verdict:trip_id triples."""
    doc = _load_output()
    parts = [f"{d['ordinal']}:{d['verdict']}:{d['trip_id']}" for d in doc["decisions"]]
    preimage = "tripfix-v1|" + str(len(doc["decisions"])) + "|" + ";".join(parts)
    expected_digest = hashlib.sha256(preimage.encode("utf-8")).hexdigest()[:16]
    assert doc["report_digest"] == expected_digest
    assert doc["report_digest"] == "d436c0725e014fb5"


def test_built_binary_is_elf_executable():
    """The compiled binary at /app/binary/tripfix has the ELF magic prefix and is executable."""
    assert os.path.exists(BINARY_PATH)
    with open(BINARY_PATH, "rb") as fh:
        head = fh.read(4)
    assert head == b"\x7fELF"
    assert os.access(BINARY_PATH, os.X_OK)


def test_source_main_present_and_nonempty():
    """The Go entrypoint /app/kernel/kernel_main/main.go is present and contains real source, not an empty file or wrapper."""
    src = "/app/kernel/kernel_main/main.go"
    assert os.path.exists(src)
    with open(src, "r") as fh:
        body = fh.read()
    assert "package main" in body
    assert len(body) > 200
