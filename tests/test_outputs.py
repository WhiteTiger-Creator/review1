"""Grades the rebuilt master server list.

Every expected value is recomputed here by reference.py, which is an
independent implementation of the same sources, and most of the grading runs
against journals generated at verification time so that nothing about the
answers can be reached from inside the image.
"""

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reference as ref

TOOL = "/app/mslist"
APP_JOURNAL = "/app/journal/session14.cap"
APP_CONFIG = "/app/msconfig.json"
APP_OUT = "/app/out"

SHIPPED_JOURNAL_SHA256 = "3e7c43b5ed03b4ed1b8c3b2f602afcd221da338627d4fe368c6a8426239a7b27"


def load_config():
    with open(APP_CONFIG, "r", encoding="utf-8") as handle:
        return json.load(handle)


CONFIG = load_config()
OFFICIAL = ref.resolve_official_hosts(CONFIG["official_hosts"])
CATALOGUE = ref.fetch_catalogue(CONFIG["external_arena_files_provider"])
OFFICIAL_IPS = [min(addresses) for _host, addresses in OFFICIAL]
CATALOGUE_NAMES = sorted(n for n in CATALOGUE if len(n) <= ref.MAX_ARENA_NAME)


def run_tool(journal_path, config_path, out_dir):
    """Run the rebuilt tool and hand back the completed process."""
    return subprocess.run(
        [TOOL, journal_path, config_path, out_dir],
        capture_output=True,
        timeout=300,
        check=False,
    )


def write_case(tmp, journal_bytes, ban_lines=(), timeout_secs=65):
    """Drop a journal, a ban list and a config into a scratch directory."""
    journal_path = os.path.join(tmp, "case.cap")
    with open(journal_path, "wb") as handle:
        handle.write(journal_bytes)
    ban_path = os.path.join(tmp, "servers.txt")
    with open(ban_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(ban_lines) + ("\n" if ban_lines else ""))
    config = dict(CONFIG)
    config["banlist_servers_path"] = ban_path
    config["server_entry_timeout_secs"] = timeout_secs
    config_path = os.path.join(tmp, "msconfig.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    return journal_path, config_path, config, ban_path


def journal_bytes(start, end, records):
    """Serialize a window and its records into the journal container."""
    path = os.path.join(tempfile.mkdtemp(), "tmp.cap")
    ref.write_journal(path, start, end, records)
    with open(path, "rb") as handle:
        return handle.read()


def expected(journal_path, config, ban_path):
    return ref.expected_outputs(journal_path, config, ban_path, OFFICIAL, CATALOGUE)


def compare_listing(produced, wanted, label):
    assert len(produced) == len(wanted), (
        f"{label}: expected {len(wanted)} entries, found {len(produced)}"
    )
    for index, (got, want) in enumerate(zip(produced, wanted)):
        clean = {k: v for k, v in want.items() if not k.startswith("_")}
        assert set(got) == set(clean), (
            f"{label}: entry {index} has keys {sorted(got)}, expected {sorted(clean)}"
        )
        for key, value in clean.items():
            if isinstance(value, float):
                assert abs(got[key] - value) < 1e-4, (
                    f"{label}: entry {index} field {key} is {got[key]}, expected {value}"
                )
            else:
                assert got[key] == value, (
                    f"{label}: entry {index} field {key} is {got[key]!r}, expected {value!r}"
                )


def compare_snapshot(produced, wanted, label):
    assert len(produced) == len(wanted), (
        f"{label}: snapshot is {len(produced)} bytes, expected {len(wanted)}"
    )
    for offset, (got, want) in enumerate(zip(produced, wanted)):
        assert got == want, (
            f"{label}: snapshot byte {offset} is 0x{got:02x}, expected 0x{want:02x}"
        )


def run_and_compare(tmp, start, end, records, ban_lines=(), timeout_secs=65, label="case"):
    """Run the tool over a generated journal and check both artefacts."""
    journal_path, config_path, config, ban_path = write_case(
        tmp, journal_bytes(start, end, records), ban_lines, timeout_secs)
    out_dir = os.path.join(tmp, "out")
    result = run_tool(journal_path, config_path, out_dir)
    assert result.returncode == 0, (
        "{}: the tool exited {}: {}".format(
            label, result.returncode, result.stderr.decode("utf-8", "replace"))
    )
    rows, _listing, snapshot = expected(journal_path, config, ban_path)
    with open(os.path.join(out_dir, "server_list.json"), "r", encoding="utf-8") as handle:
        produced = json.load(handle)
    compare_listing(produced, rows, label)
    with open(os.path.join(out_dir, "snapshot.bin"), "rb") as handle:
        compare_snapshot(handle.read(), snapshot, label)
    return produced


def fresh_journal(seed):
    """A journal built from addresses and arenas resolved at grading time."""
    foreign = [f"zz_unpublished_{seed}", f"zz_local_test_{seed}"]
    published = [n for n in CATALOGUE_NAMES if n not in foreign][:8]
    return ref.generate_journal(seed, OFFICIAL_IPS, published, foreign)


def test_agent_left_both_artefacts():
    """The tool exists and the run over the recorded journal left both files."""
    assert os.path.isfile(TOOL), "/app/mslist was not created"
    assert os.access(TOOL, os.X_OK), "/app/mslist is not executable"
    assert os.path.isfile(os.path.join(APP_OUT, "server_list.json")), (
        "/app/out/server_list.json is missing"
    )
    assert os.path.isfile(os.path.join(APP_OUT, "snapshot.bin")), (
        "/app/out/snapshot.bin is missing"
    )


def test_recorded_journal_untouched():
    """The recorded journal is still the one that shipped with the image."""
    with open(APP_JOURNAL, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    assert digest == SHIPPED_JOURNAL_SHA256, "the recorded journal was modified"


def test_recorded_server_list():
    """The published list rebuilt from the recorded journal matches field by field."""
    rows, _listing, _snapshot = expected(APP_JOURNAL, CONFIG, CONFIG["banlist_servers_path"])
    with open(os.path.join(APP_OUT, "server_list.json"), "r", encoding="utf-8") as handle:
        produced = json.load(handle)
    compare_listing(produced, rows, "recorded journal")


def test_recorded_snapshot():
    """The snapshot rebuilt from the recorded journal matches byte for byte."""
    _rows, _listing, snapshot = expected(APP_JOURNAL, CONFIG, CONFIG["banlist_servers_path"])
    with open(os.path.join(APP_OUT, "snapshot.bin"), "rb") as handle:
        compare_snapshot(handle.read(), snapshot, "recorded journal")


@pytest.mark.parametrize("seed", [4101, 4102, 4103])
def test_unseen_journals(seed):
    """Journals generated at grading time rebuild correctly as well."""
    start, end, records, ban_lines = fresh_journal(seed)
    with tempfile.TemporaryDirectory() as tmp:
        run_and_compare(tmp, start, end, records, ban_lines,
                        label=f"journal {seed}")


def test_official_hosts_are_resolved():
    """Servers hosted on the configured official hosts are reported as official."""
    rng_start = 1699000000.0
    records = []
    for index, ip in enumerate(OFFICIAL_IPS):
        beat = ref.Heartbeat(
            server_name=f"[US] Resolved Fleet#{index + 1}",
            current_arena=CATALOGUE_NAMES[index % len(CATALOGUE_NAMES)],
            game_mode="Bomb Defusal",
            num_online_humans=2,
            num_online=3,
            server_slots=8,
            server_version="2.3.0-pre1",
            ranked_state=1 if index % 2 == 0 else 0,
        )
        records.append(ref.Record(rng_start + 1.0 + index, ip, 8412 + index,
                                  ref.encode_request(ref.REQ_HEARTBEAT, beat)))
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, rng_start, rng_start + 40.0, records,
                                   label="official hosts")
    hosts = {host for host, _addresses in OFFICIAL}
    marked = [row for row in produced if row["is_official"]]
    assert len(marked) == len(OFFICIAL_IPS), "not every official address was recognised"
    for row in marked:
        assert row["official_url"].split(":")[0] in hosts
        assert row["site_displayed_address"] == row["official_url"]
        assert row["webrtc_id"] != "", "an official server was given no alias"


def test_published_arenas_are_recognised():
    """Arenas are checked against the catalogue the provider is serving."""
    start = 1699100000.0
    records = []
    names = CATALOGUE_NAMES[:4] + ["zz_not_published_a", "zz_not_published_b"]
    for index, arena in enumerate(names):
        beat = ref.Heartbeat(
            server_name=f"Catalogue Probe {index}",
            current_arena=arena,
            game_mode="Gun Game",
            num_online_humans=1,
            num_online=1,
            server_slots=4,
            server_version="2.2.4",
        )
        records.append(ref.Record(start + 1.0 + index, f"203.0.113.{index + 1}", 8412,
                                  ref.encode_request(ref.REQ_HEARTBEAT, beat)))
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 30.0, records, label="catalogue")
    by_arena = {row["arena"]: row for row in produced}
    for arena in CATALOGUE_NAMES[:4]:
        assert by_arena[arena]["arena_in_catalogue"] is True
        assert by_arena[arena]["arena_author"] == CATALOGUE[arena]
    for arena in ("zz_not_published_a", "zz_not_published_b"):
        assert by_arena[arena]["arena_in_catalogue"] is False
        assert by_arena[arena]["arena_author"] == ""


def test_timeout_boundary_restarts_the_registration():
    """A heartbeat that lands exactly on the timeout opens a new registration."""
    start = 1699200000.0
    arena = CATALOGUE_NAMES[0]

    def beat(name):
        return ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
            server_name=name, current_arena=arena, game_mode="Bomb Defusal",
            num_online_humans=1, num_online=2, server_slots=6, server_version="2.2.4"))

    records = [
        ref.Record(start + 1.0, "198.51.100.7", 8412, beat("Exactly On Time")),
        ref.Record(start + 66.0, "198.51.100.7", 8412, beat("Exactly On Time")),
        ref.Record(start + 10.0, "198.51.100.8", 8412, beat("Comfortably Early")),
        ref.Record(start + 70.0, "198.51.100.8", 8412, beat("Comfortably Early")),
    ]
    records.sort(key=lambda r: r.arrived_at)
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 90.0, records, label="timeout boundary")
    by_ip = {row["ip"]: row for row in produced}
    restarted = by_ip["198.51.100.7:8412"]
    assert restarted["heartbeats_accepted"] == 1, (
        "the registration should have restarted at the timeout boundary"
    )
    assert abs(restarted["time_hosted"] - (start + 66.0)) < 1e-4
    kept = by_ip["198.51.100.8:8412"]
    assert kept["heartbeats_accepted"] == 2, "a live registration should have been kept"
    assert abs(kept["time_hosted"] - (start + 10.0)) < 1e-4


def test_undecodable_payload_drops_the_registration():
    """A payload the master server cannot decode is not simply skipped."""
    start = 1699300000.0
    arena = CATALOGUE_NAMES[0]
    good = ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
        server_name="Flaky Link", current_arena=arena, game_mode="Bomb Defusal",
        num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4"))
    survivor = ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
        server_name="Sturdy Link", current_arena=arena, game_mode="Bomb Defusal",
        num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4"))
    records = [
        ref.Record(start + 1.0, "198.51.100.20", 8412, good),
        ref.Record(start + 2.0, "198.51.100.21", 8412, survivor),
        ref.Record(start + 3.0, "198.51.100.20", 8412, good[:13]),
        ref.Record(start + 4.0, "198.51.100.22", 8412, good[:13]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 20.0, records, label="undecodable")
    listed = {row["ip"] for row in produced}
    assert "198.51.100.20:8412" not in listed, "a mangled datagram left the entry in place"
    assert "198.51.100.21:8412" in listed, "an unrelated server was dropped"
    assert "198.51.100.22:8412" not in listed


def test_ban_list_is_enforced():
    """Banned addresses and banned server names are handled as the game handles them."""
    start = 1699400000.0
    arena = CATALOGUE_NAMES[0]

    def beat(name):
        return ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
            server_name=name, current_arena=arena, game_mode="Free for All",
            num_online_humans=1, num_online=1, server_slots=4, server_version="2.1.9"))

    records = [
        ref.Record(start + 1.0, "198.51.100.30", 8412, beat("Blocked Address")),
        ref.Record(start + 2.0, "198.51.100.31", 8412, beat("Fine Name")),
        ref.Record(start + 3.0, "198.51.100.31", 8412, beat("SHOUTY rude name")),
        ref.Record(start + 4.0, "198.51.100.32", 8412, beat("Shouty Rude Name")),
    ]
    bans = ["198.51.100.30", "203.0.113.55 Shouty rude NAME"]
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 20.0, records, bans, label="ban list")
    by_ip = {row["ip"]: row for row in produced}
    assert "198.51.100.30:8412" not in by_ip, "a banned address was listed"
    assert "198.51.100.32:8412" not in by_ip, "a banned name was listed"
    kept = by_ip["198.51.100.31:8412"]
    assert kept["name"] == "Fine Name", "a banned rename was applied to a live registration"
    assert kept["heartbeats_accepted"] == 1


def test_rejected_heartbeats_leave_the_entry_alone():
    """Heartbeats the game refuses do not update, and do not remove, a registration."""
    start = 1699500000.0
    arena = CATALOGUE_NAMES[0]

    def beat(name, arena_name=arena, mode="Duel of Honor"):
        return ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
            server_name=name, current_arena=arena_name, game_mode=mode,
            num_online_humans=2, num_online=4, server_slots=8, server_version="2.3.0-pre1"))

    records = [
        ref.Record(start + 1.0, "198.51.100.40", 8412, beat("Original Name")),
        ref.Record(start + 2.0, "198.51.100.40", 8412, beat("Tabbed\tName")),
        ref.Record(start + 3.0, "198.51.100.40", 8412, beat("    ")),
        ref.Record(start + 4.0, "198.51.100.40", 8412, beat("Original Name", arena_name="")),
        ref.Record(start + 5.0, "198.51.100.40", 8412, beat("Original Name", mode="")),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 20.0, records, label="rejected heartbeats")
    assert len(produced) == 1
    assert produced[0]["name"] == "Original Name"
    assert produced[0]["heartbeats_accepted"] == 1


def test_servers_can_ask_to_stay_off_the_list():
    """A server whose last heartbeat opts out is tracked but not published."""
    start = 1699600000.0
    arena = CATALOGUE_NAMES[0]

    def beat(name, show):
        return ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
            server_name=name, current_arena=arena, game_mode="Bomb Defusal",
            num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4",
            show_on_server_list=show))

    records = [
        ref.Record(start + 1.0, "198.51.100.50", 8412, beat("Private Scrim", True)),
        ref.Record(start + 2.0, "198.51.100.50", 8412, beat("Private Scrim", False)),
        ref.Record(start + 3.0, "198.51.100.51", 8412, beat("Hidden Then Public", False)),
        ref.Record(start + 4.0, "198.51.100.51", 8412, beat("Hidden Then Public", True)),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 20.0, records, label="hidden servers")
    listed = {row["ip"] for row in produced}
    assert "198.51.100.50:8412" not in listed
    assert "198.51.100.51:8412" in listed


def test_goodbye_and_noise_are_handled():
    """Farewells remove a registration while other request kinds never touch it."""
    start = 1699700000.0
    arena = CATALOGUE_NAMES[0]
    beat = ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
        server_name="Chatty Host", current_arena=arena, game_mode="Bomb Defusal",
        num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4"))
    records = [
        ref.Record(start + 1.0, "198.51.100.60", 8412, beat),
        ref.Record(start + 2.0, "198.51.100.60", 8412,
                   ref.encode_request(ref.REQ_TELL_ME_MY_ADDRESS, start + 2.0)),
        ref.Record(start + 3.0, "198.51.100.60", 8412,
                   ref.encode_request(ref.REQ_WEBRTC, (42, "offer"))),
        ref.Record(start + 4.0, "198.51.100.60", 8412, ref.encode_request(ref.REQ_DUMMY_INT, 9)),
        ref.Record(start + 5.0, "198.51.100.61", 8412, beat),
        ref.Record(start + 6.0, "198.51.100.61", 8412, ref.encode_request(ref.REQ_GOODBYE)),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        produced = run_and_compare(tmp, start, start + 20.0, records, label="goodbye and noise")
    listed = {row["ip"] for row in produced}
    assert "198.51.100.60:8412" in listed, "an unrelated request removed a registration"
    assert "198.51.100.61:8412" not in listed, "a farewell was ignored"
    assert len(produced) == 1


def broken_journals():
    """Every way a journal can be unusable, as one named case each."""
    start = 1699800000.0
    beat = ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
        server_name="Some Host", current_arena=CATALOGUE_NAMES[0], game_mode="Bomb Defusal",
        num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4"))
    records = [
        ref.Record(start + 1.0, "198.51.100.70", 8412, beat),
        ref.Record(start + 2.0, "198.51.100.71", 8412, beat),
    ]
    good = journal_bytes(start, start + 20.0, records)

    cases = {}
    cases["bad magic"] = b"HMSJRNL2" + good[8:]
    cases["short header"] = good[:20]
    cases["count too high"] = good[:8] + struct.pack("<I", 9) + good[12:]
    cases["trailing bytes"] = good + b"\x00\x07"
    cases["not ipv4"] = bytearray(good)
    cases["not ipv4"][36] = 6
    cases["not ipv4"] = bytes(cases["not ipv4"])
    cases["window inverted"] = good[:12] + struct.pack("<dd", start + 20.0, start) + good[28:]
    cases["time goes backwards"] = journal_bytes(start, start + 20.0, [
        ref.Record(start + 5.0, "198.51.100.70", 8412, beat),
        ref.Record(start + 2.0, "198.51.100.71", 8412, beat),
    ])
    cases["payload past the end"] = good[:-4]
    return cases


@pytest.mark.parametrize("case", sorted(broken_journals()))
def test_unusable_journals_fail_loudly(case):
    """An unusable journal exits with status 2 and leaves no report behind."""
    blob = broken_journals()[case]
    with tempfile.TemporaryDirectory() as tmp:
        journal_path, config_path, _config, _ban = write_case(tmp, blob)
        out_dir = os.path.join(tmp, "out")
        result = run_tool(journal_path, config_path, out_dir)
        assert result.returncode == 2, (
            f"{case}: expected status 2, got {result.returncode}"
        )
        leftovers = os.listdir(out_dir) if os.path.isdir(out_dir) else []
        assert leftovers == [], f"{case}: a partial report was left behind: {leftovers}"


def test_output_directory_is_created():
    """A missing output directory is created rather than treated as an error."""
    start = 1699900000.0
    beat = ref.encode_request(ref.REQ_HEARTBEAT, ref.Heartbeat(
        server_name="Lonely Host", current_arena=CATALOGUE_NAMES[0], game_mode="Bomb Defusal",
        num_online_humans=1, num_online=1, server_slots=4, server_version="2.2.4"))
    records = [ref.Record(start + 1.0, "198.51.100.80", 8412, beat)]
    with tempfile.TemporaryDirectory() as tmp:
        journal_path, config_path, _config, _ban = write_case(
            tmp, journal_bytes(start, start + 10.0, records))
        out_dir = os.path.join(tmp, "nested", "report")
        result = run_tool(journal_path, config_path, out_dir)
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        assert os.path.isfile(os.path.join(out_dir, "server_list.json"))
        assert os.path.isfile(os.path.join(out_dir, "snapshot.bin"))
