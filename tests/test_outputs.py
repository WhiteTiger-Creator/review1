"""Behavioral verifier for OpenLDAP delta-syncrepl cookie recovery."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers import (
    ADMIN_DN,
    ADMIN_PW,
    BACKUP,
    BASE_DN,
    CONSUMER_URI,
    PROVIDER_URI,
    READER_DN,
    READER_PW,
    REPLICATOR_DN,
    REPLICATOR_PW,
    STATUS_PATH,
    VERIFIER_BASE,
    accesslog_has_csn,
    accesslog_search_as_replicator,
    add_group_with_member,
    add_person,
    add_verifier_record,
    apply_provider_ldif,
    assert_no_stale_report,
    check_replica,
    compare_trees_via_lib,
    context_csn,
    deterministic_token,
    dn_exists,
    ensure_verifier_suite_baseline,
    entry_count,
    establish_primary_suffix_lag_with_synced_verifier,
    ldapmodify_as,
    ldapsearch,
    ldapsearch_as,
    load_status,
    make_consumer_backup,
    parse_accesslog_fields,
    process_count_for_slapd_role,
    read_pidfile,
    remove_generated_slapd_confs,
    reset_consumer_data,
    run_cmd,
    server_id_for_role,
    sha256_file,
    slapadd_consumer_offline,
    slapmodify_consumer_offline,
    start_ldap,
    stop_ldap,
    trees_equivalent,
    trees_equivalent_for_base,
    wait_for_base_sync,
    wait_for_sync,
    wait_sync_via_lib,
)


@pytest.fixture(scope="session", autouse=True)
def verifier_suite_baseline():
    ensure_verifier_suite_baseline()


@pytest.fixture(autouse=True)
def ldap_lifecycle():
    stop_ldap()
    yield
    stop_ldap()


def test_clean_consumer_initial_sync():
    """A wiped consumer must converge to the provider tree."""
    reset_consumer_data()
    assert trees_equivalent()


def test_incremental_changes_converge():
    """Adds, deletes, and renames on the provider must replicate."""
    reset_consumer_data()
    token = deterministic_token("incremental_changes_converge")
    apply_provider_ldif(
        f"""dn: uid=v-{token},ou=people,{BASE_DN}
changetype: add
objectClass: inetOrgPerson
cn: Verifier {token}
sn: {token}
uid: v-{token}
mail: {token}@example.com
description: verifier add
"""
    )
    wait_for_sync()
    apply_provider_ldif(
        f"""dn: uid=v-{token},ou=people,{BASE_DN}
changetype: delete
"""
    )
    wait_for_sync()
    assert trees_equivalent()


def test_restore_backup_then_converge():
    """Restored consumer state must recover to provider equivalence."""
    reset_consumer_data()
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(BACKUP)], check=False)
    assert proc.returncode == 0, proc.stderr
    wait_for_sync()
    assert trees_equivalent()


def test_restart_preserves_convergence():
    """Provider and consumer must remain equivalent across restarts."""
    reset_consumer_data()
    wait_for_sync()
    stop_ldap()
    start_ldap()
    wait_for_sync()
    stop_ldap()
    start_ldap()
    wait_for_sync()
    assert trees_equivalent()


def test_reader_denied_accesslog():
    """Ordinary users must not read access-log contents."""
    start_ldap()
    proc = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-D",
            READER_DN,
            "-w",
            READER_PW,
            "-b",
            "cn=accesslog",
            "(objectClass=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0 or "dn:" not in proc.stdout


def test_invalid_schema_change_rejected():
    """Invalid schema attributes must be rejected on modify."""
    start_ldap()
    proc = subprocess.run(
        [
            "ldapmodify",
            "-x",
            "-H",
            PROVIDER_URI,
            "-D",
            ADMIN_DN,
            "-w",
            ADMIN_PW,
        ],
        input=(
            f"dn: uid=bob,ou=people,{BASE_DN}\n"
            "changetype: modify\n"
            "add: unknownVerifierAttribute\n"
            "unknownVerifierAttribute: blocked\n"
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_verifier_suffix_replicates():
    """Verifier-owned entries under the internal suffix must replicate."""
    reset_consumer_data()
    token = deterministic_token("verifier_suffix_replicates")
    apply_provider_ldif(
        f"""dn: uid=probe-{token},ou=records,{VERIFIER_BASE}
changetype: add
objectClass: inetOrgPerson
cn: Probe {token}
sn: {token}
uid: probe-{token}
description: verifier suffix probe
"""
    )
    wait_for_base_sync(VERIFIER_BASE)
    provider = ldapsearch(
        PROVIDER_URI,
        ADMIN_DN,
        ADMIN_PW,
        "-b",
        VERIFIER_BASE,
        f"(uid=probe-{token})",
        "dn",
        "description",
    )
    consumer = ldapsearch(
        CONSUMER_URI,
        ADMIN_DN,
        ADMIN_PW,
        "-b",
        VERIFIER_BASE,
        f"(uid=probe-{token})",
        "dn",
        "description",
    )
    assert f"uid=probe-{token}" in provider
    assert provider.strip() == consumer.strip()


def test_status_report_matches_live_state():
    """Replication status JSON must mirror live BASE_DN LDAP measurements."""
    reset_consumer_data()
    wait_for_sync()
    result = check_replica(STATUS_PATH)
    assert result.returncode == 0, result.stderr
    status = load_status(STATUS_PATH)
    assert status["provider_uri"] == PROVIDER_URI
    assert status["consumer_uri"] == CONSUMER_URI
    assert status["equivalent"] is True
    assert status["provider_entry_count"] == entry_count(PROVIDER_URI, BASE_DN)
    assert status["consumer_entry_count"] == entry_count(CONSUMER_URI, BASE_DN)
    assert status["provider_context_csn"] == context_csn(PROVIDER_URI, BASE_DN)
    assert status["consumer_context_csn"] == context_csn(CONSUMER_URI, BASE_DN)
    assert status["recovery_mode"] in {"none", "delta", "refresh"}
    assert isinstance(status["checked_at"], int)


def test_backup_archive_is_immutable():
    """Bundled backup inputs must remain unchanged."""
    before = BACKUP.read_bytes()
    reset_consumer_data()
    run_cmd(["/app/bin/restore-consumer", str(BACKUP)], check=False)
    after = BACKUP.read_bytes()
    assert before == after


def test_sourceable_libs_preserve_shell_options():
    """Sourceable /app/lib modules must not enable errexit in the caller shell."""
    script = r"""
set +e
set +u
set +o pipefail
before="$(set +o)"
source /app/lib/common.sh
source /app/lib/compare-trees.sh
source /app/lib/wait-sync.sh
source /app/lib/write-status.sh
after="$(set +o)"
if [ "$before" != "$after" ]; then
  exit 20
fi
if [ -f /app/ldap/runtime/provider.pid ] && kill -0 "$(cat /app/ldap/runtime/provider.pid)" 2>/dev/null; then
  exit 21
fi
if [ -f /app/ldap/runtime/consumer.pid ] && kill -0 "$(cat /app/ldap/runtime/consumer.pid)" 2>/dev/null; then
  exit 22
fi
false
echo source-shell-survived
"""
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "source-shell-survived" in result.stdout


def test_delta_restore_replays_delete_tombstone_without_resurrection(tmp_path):
    """Delta restore must replay provider deletes and not resurrect removed DNs."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("delta_restore_delete")
    person_dn = add_person(f"del-{token}")
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, name="delta-delete.tar")
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid=del-{token})")
    assert trees_equivalent()


def test_delta_restore_replays_modrdn_and_attribute_replace_together(tmp_path):
    """Delta restore must apply combined rename and attribute replacement."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("delta_modrdn_replace")
    old_uid = f"rn-{token}"
    new_uid = f"rn2-{token}"
    person_dn = add_person(old_uid, description="rename target")
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, name="delta-modrdn.tar")
    apply_provider_ldif(
        f"""dn: {person_dn}
changetype: modrdn
newrdn: uid={new_uid}
deleteoldrdn: 1
"""
    )
    apply_provider_ldif(
        f"""dn: uid={new_uid},ou=people,{BASE_DN}
changetype: modify
replace: mail
mail: {new_uid}@example.com
-
replace: description
description: renamed and replaced
"""
    )
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid={old_uid})")
    assert dn_exists(CONSUMER_URI, BASE_DN, f"(uid={new_uid})")
    consumer = ldapsearch(
        CONSUMER_URI,
        ADMIN_DN,
        ADMIN_PW,
        "-b",
        BASE_DN,
        f"(uid={new_uid})",
        "mail",
        "description",
    )
    assert f"{new_uid}@example.com" in consumer
    assert "renamed and replaced" in consumer


def test_delta_restore_handles_add_modify_delete_sequence_for_same_uid(tmp_path):
    """Delta restore must converge after add/modify/delete on one generated uid."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("delta_amd_sequence")
    uid = f"amd-{token}"
    backup = make_consumer_backup(tmp_path, name="delta-amd.tar")
    person_dn = add_person(uid, description="phase-one")
    wait_for_sync()
    apply_provider_ldif(
        f"""dn: {person_dn}
changetype: modify
replace: description
description: phase-two
"""
    )
    wait_for_sync()
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid={uid})")
    assert trees_equivalent()


def test_delta_restore_preserves_group_membership_after_member_rename(tmp_path):
    """Delta restore must keep group membership on the renamed member DN without stale values."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("delta_group_member_rename")
    member_uid = f"mem-{token}"
    group_cn = f"grp-{token}"
    member_dn = add_person(member_uid, description="group member")
    group_dn = add_group_with_member(group_cn, member_dn)
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, name="delta-group.tar")
    new_uid = f"mem2-{token}"
    new_member_dn = f"uid={new_uid},ou=people,{BASE_DN}"
    apply_provider_ldif(
        f"""dn: {member_dn}
changetype: modrdn
newrdn: uid={new_uid}
deleteoldrdn: 1
"""
    )
    apply_provider_ldif(
        f"""dn: {group_dn}
changetype: modify
delete: member
member: {member_dn}
-
add: member
member: {new_member_dn}
"""
    )
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    group_out = ldapsearch(
        CONSUMER_URI,
        ADMIN_DN,
        ADMIN_PW,
        "-b",
        group_dn,
        "(objectClass=*)",
        "member",
    )
    assert new_member_dn in group_out
    assert member_dn not in group_out
    assert trees_equivalent()


def test_restore_missing_cookie_file_forces_refresh_and_converges(tmp_path):
    """Backups without meta/context-csn must refresh safely and converge."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("missing_cookie_refresh")
    person_dn = add_person(f"missing-{token}")
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, include_cookie=False, name="no-cookie.tar")
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert trees_equivalent()
    result = check_replica(STATUS_PATH)
    assert result.returncode == 0
    status = load_status(STATUS_PATH)
    assert status["recovery_mode"] == "refresh"


def test_restore_malformed_cookie_forces_refresh_without_partial_state(tmp_path):
    """Malformed retained cookies must trigger refresh without leaving stale entries."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("malformed_cookie_refresh")
    stale_dn = add_person(f"stale-{token}")
    wait_for_sync()
    backup = make_consumer_backup(
        tmp_path,
        cookie_override="not-a-valid-csn-token",
        name="bad-cookie.tar",
    )
    apply_provider_ldif(f"dn: {stale_dn}\nchangetype: delete\n")
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid=stale-{token})")
    assert trees_equivalent()
    assert check_replica(STATUS_PATH).returncode == 0
    status = load_status(STATUS_PATH)
    assert status["recovery_mode"] == "refresh"


def test_restore_trimmed_accesslog_cookie_falls_back_to_refresh():
    """Bundled backup with trimmed accesslog cookie must refresh and remove stale entries."""
    reset_consumer_data()
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(BACKUP)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert trees_equivalent()
    assert not dn_exists(CONSUMER_URI, BASE_DN, "(uid=alice)")
    assert dn_exists(CONSUMER_URI, BASE_DN, "(uid=bob)")
    assert check_replica(STATUS_PATH).returncode == 0
    status = load_status(STATUS_PATH)
    assert status["recovery_mode"] == "refresh"


def test_restore_fails_cleanly_for_unreadable_or_invalid_archive(tmp_path):
    """Invalid archives must fail before mutating a synchronized consumer tree."""
    reset_consumer_data()
    wait_for_sync()
    before = ldapsearch(CONSUMER_URI, ADMIN_DN, ADMIN_PW, "-b", BASE_DN, "(objectClass=*)", "dn")
    invalid = tmp_path / "invalid.tar"
    invalid.write_text("this is not a tar archive\n")
    proc = run_cmd(["/app/bin/restore-consumer", str(invalid)], check=False)
    assert proc.returncode != 0
    after = ldapsearch(CONSUMER_URI, ADMIN_DN, ADMIN_PW, "-b", BASE_DN, "(objectClass=*)", "dn")
    assert before.strip() == after.strip()


def test_restore_returns_only_after_live_tree_equivalence_no_extra_check_needed(tmp_path):
    """Successful restore must already match provider tree without follow-up recovery calls."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("restore_immediate_equiv")
    person_dn = add_person(f"immediate-{token}")
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, name="immediate.tar")
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert trees_equivalent()


def test_restore_backup_archive_sha256_unchanged_after_delta_and_refresh_paths(tmp_path):
    """Restore must not mutate backup archive bytes for delta or refresh paths."""
    reset_consumer_data()
    wait_for_sync()
    bundled_hash = sha256_file(BACKUP)
    token = deterministic_token("archive_immutable_paths")
    person_dn = add_person(f"hash-{token}")
    wait_for_sync()
    delta_backup = make_consumer_backup(tmp_path, name="hash-delta.tar")
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    run_cmd(["/app/bin/restore-consumer", str(delta_backup)], check=False)
    assert sha256_file(BACKUP) == bundled_hash
    reset_consumer_data()
    wait_for_sync()
    run_cmd(["/app/bin/restore-consumer", str(BACKUP)], check=False)
    assert sha256_file(BACKUP) == bundled_hash


def test_check_replica_failure_removes_or_replaces_stale_success_report(tmp_path):
    """Failed check-replica must not leave a prior success report reusable."""
    reset_consumer_data()
    wait_for_sync()
    report = tmp_path / "status.json"
    assert check_replica(report).returncode == 0
    previous = report.read_bytes()
    stop_ldap()
    result = check_replica(report)
    assert result.returncode != 0
    assert_no_stale_report(report, previous)


def test_check_replica_output_parent_file_collision_is_failure_atomic(tmp_path):
    """A file parent path must make check-replica fail without truncating other reports."""
    reset_consumer_data()
    wait_for_sync()
    safe_report = tmp_path / "safe.json"
    assert check_replica(safe_report).returncode == 0
    safe_bytes = safe_report.read_bytes()
    collision_parent = tmp_path / "not-a-dir"
    collision_parent.write_text("blocker\n")
    blocked_report = collision_parent / "status.json"
    result = check_replica(blocked_report)
    assert result.returncode != 0
    assert safe_report.read_bytes() == safe_bytes


def test_status_counts_exclude_accesslog_and_verifier_suffix_after_extra_entries():
    """Status entry counts must include only dc=example,dc=com subtree entries."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("status_counts_primary_only")
    before_count = entry_count(PROVIDER_URI, BASE_DN)
    add_verifier_record(f"vcnt-{token}")
    wait_for_base_sync(VERIFIER_BASE)
    result = check_replica(STATUS_PATH)
    assert result.returncode == 0
    status = load_status(STATUS_PATH)
    assert status["provider_entry_count"] == entry_count(PROVIDER_URI, BASE_DN)
    assert status["consumer_entry_count"] == entry_count(CONSUMER_URI, BASE_DN)
    assert status["provider_entry_count"] == before_count
    verifier_count = entry_count(PROVIDER_URI, VERIFIER_BASE)
    assert verifier_count > 0
    assert status["provider_entry_count"] != before_count + verifier_count


def test_status_context_csn_is_base_scope_single_string_not_multisuffix_summary():
    """Status CSN fields must be single base-scope strings for the primary suffix only."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("status_csn_primary")
    add_person(f"csn-{token}")
    add_verifier_record(f"vcsn-{token}")
    wait_for_sync()
    wait_for_base_sync(VERIFIER_BASE)
    status = load_status(STATUS_PATH) if STATUS_PATH.exists() else {}
    check_replica(STATUS_PATH)
    status = load_status(STATUS_PATH)
    provider_csn = context_csn(PROVIDER_URI, BASE_DN)
    consumer_csn = context_csn(CONSUMER_URI, BASE_DN)
    assert isinstance(status["provider_context_csn"], str)
    assert isinstance(status["consumer_context_csn"], str)
    assert status["provider_context_csn"] == provider_csn
    assert status["consumer_context_csn"] == consumer_csn
    assert "," not in status["provider_context_csn"]
    assert VERIFIER_BASE not in status["provider_context_csn"]


def test_status_report_changes_after_live_provider_mutation_not_static_json():
    """Regenerated status must reflect new live counts or CSNs after provider mutation."""
    reset_consumer_data()
    wait_for_sync()
    check_replica(STATUS_PATH)
    before = load_status(STATUS_PATH)
    token = deterministic_token("status_live_mutation")
    add_person(f"live-{token}")
    wait_for_sync()
    check_replica(STATUS_PATH)
    after = load_status(STATUS_PATH)
    assert after["checked_at"] >= before["checked_at"]
    assert (
        after["provider_entry_count"] > before["provider_entry_count"]
        or after["provider_context_csn"] != before["provider_context_csn"]
        or after["consumer_entry_count"] > before["consumer_entry_count"]
    )


def test_verifier_suffix_lag_does_not_make_primary_check_replica_fail():
    """check-replica success must depend only on primary suffix equivalence."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("verifier_lag_ok")
    before_count = entry_count(PROVIDER_URI, BASE_DN)
    add_verifier_record(f"vlag-{token}")
    wait_for_base_sync(VERIFIER_BASE)
    assert check_replica(STATUS_PATH).returncode == 0
    status = load_status(STATUS_PATH)
    assert status["provider_entry_count"] == before_count
    assert status["provider_entry_count"] == entry_count(PROVIDER_URI, BASE_DN)
    assert dn_exists(CONSUMER_URI, VERIFIER_BASE, f"(uid=vlag-{token})")


def test_primary_suffix_lag_fails_even_when_verifier_suffix_is_synced():
    """Primary divergence must fail check-replica even if verifier suffix matches."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("primary_lag_fail")
    verifier_dn = establish_primary_suffix_lag_with_synced_verifier(token)
    assert check_replica(STATUS_PATH).returncode != 0
    assert trees_equivalent_for_base(VERIFIER_BASE)
    assert ldapsearch(CONSUMER_URI, ADMIN_DN, ADMIN_PW, "-b", verifier_dn, "(objectClass=*)", "dn")


def test_reader_can_read_primary_people_but_not_accesslog_or_verifier_suffix():
    """Reader binds may read primary people entries but not accesslog or verifier suffix."""
    reset_consumer_data()
    wait_for_sync()
    primary = ldapsearch_as(PROVIDER_URI, READER_DN, READER_PW, "-b", f"ou=people,{BASE_DN}", "(uid=*)", "dn")
    assert "dn:" in primary
    accesslog_proc = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-D",
            READER_DN,
            "-w",
            READER_PW,
            "-b",
            "cn=accesslog",
            "(objectClass=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert accesslog_proc.returncode != 0 or "dn:" not in accesslog_proc.stdout
    verifier_proc = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-D",
            READER_DN,
            "-w",
            READER_PW,
            "-b",
            VERIFIER_BASE,
            "(objectClass=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verifier_proc.returncode != 0 or "dn:" not in verifier_proc.stdout


def test_replicator_can_read_accesslog_but_cannot_modify_primary_entries():
    """Replicator may read accesslog audit data but cannot write primary entries."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("replicator_acl")
    add_person(f"rep-{token}")
    wait_for_sync()
    log = accesslog_search_as_replicator("(reqDN=*)", "dn", "reqDN")
    assert "reqDN:" in log
    proc = ldapmodify_as(
        REPLICATOR_DN,
        REPLICATOR_PW,
        f"""dn: uid=rep-{token},ou=people,{BASE_DN}
changetype: modify
replace: description
description: blocked write
""",
    )
    assert proc.returncode != 0


def test_anonymous_bind_cannot_enumerate_primary_or_accesslog_entries():
    """Anonymous searches must not disclose primary users or accesslog entries."""
    reset_consumer_data()
    wait_for_sync()
    primary = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-b",
            f"ou=people,{BASE_DN}",
            "(uid=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "uid=alice" not in primary.stdout
    accesslog = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-b",
            "cn=accesslog",
            "(objectClass=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "dn:" not in accesslog.stdout


def test_accesslog_contains_reqdn_reqmod_and_entrycsn_for_replayable_changes():
    """Accesslog must retain reqDN, reqMod, and entryCSN for replayable provider changes."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("accesslog_audit_fields")
    uid = f"alog-{token}"
    person_dn = add_person(uid, description="audit-one")
    wait_for_sync()
    apply_provider_ldif(
        f"""dn: {person_dn}
changetype: modify
replace: description
description: audit-two
"""
    )
    wait_for_sync()
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    output = accesslog_search_as_replicator(f"(reqDN={person_dn})", "reqDN", "reqMod", "entryCSN")
    if not output.strip():
        output = accesslog_search_as_replicator(f"(reqDN=*{uid}*)", "reqDN", "reqMod", "entryCSN")
    entries = parse_accesslog_fields(output)
    assert entries, "expected accesslog entries for generated changes"
    has_reqdn = any(entry.get("reqDN") for entry in entries)
    has_reqmod = any(entry.get("reqMod") for entry in entries)
    has_entrycsn = any(entry.get("entryCSN") for entry in entries)
    assert has_reqdn and has_reqmod and has_entrycsn


def test_accesslog_cookie_probe_matches_entrycsn_and_reqmod_paths():
    """accesslog-has-csn must accept CSNs from entryCSN and reqMod and reject fabricated CSNs."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("cookie_probe")
    person_dn = add_person(f"probe-{token}")
    wait_for_sync()
    live_csn = context_csn(PROVIDER_URI, BASE_DN)
    assert live_csn
    assert accesslog_has_csn(live_csn) == 0
    apply_provider_ldif(
        f"""dn: {person_dn}
changetype: modify
replace: description
description: probe-reqmod
"""
    )
    wait_for_sync()
    assert accesslog_has_csn(live_csn) == 0 or accesslog_has_csn(context_csn(PROVIDER_URI, BASE_DN)) == 0
    assert accesslog_has_csn("20990101000000.000000Z#000000#000000") != 0


def test_repeated_start_does_not_spawn_duplicate_slapd_processes():
    """Repeated start-ldap calls must keep one live slapd process per role."""
    reset_consumer_data()
    wait_for_sync()
    for _ in range(3):
        start_ldap()
    assert process_count_for_slapd_role("provider") == 1
    assert process_count_for_slapd_role("consumer") == 1
    for role in ("provider", "consumer"):
        pid = read_pidfile(role)
        assert pid is not None
        assert process_count_for_slapd_role(role) == 1


def test_stop_then_start_ignores_stale_pid_files_and_recovers():
    """Restart after stop must ignore stale PID files and restore healthy listeners."""
    reset_consumer_data()
    wait_for_sync()
    stop_ldap()
    for role in ("provider", "consumer"):
        stale = Path(f"/app/ldap/runtime/{role}.pid")
        stale.write_text("999999\n")
    start_ldap()
    wait_for_sync()
    assert process_count_for_slapd_role("provider") == 1
    assert process_count_for_slapd_role("consumer") == 1
    assert trees_equivalent()


def test_server_ids_are_stable_distinct_and_rendered_after_config_regeneration():
    """Provider and consumer server IDs must remain distinct after slapd.conf regeneration."""
    reset_consumer_data()
    wait_for_sync()
    before_provider = server_id_for_role("provider")
    before_consumer = server_id_for_role("consumer")
    assert before_provider and before_consumer
    assert before_provider != before_consumer
    remove_generated_slapd_confs()
    stop_ldap()
    start_ldap()
    wait_for_sync()
    after_provider = server_id_for_role("provider")
    after_consumer = server_id_for_role("consumer")
    assert after_provider == before_provider
    assert after_consumer == before_consumer
    assert after_provider != after_consumer


def test_sourceable_libraries_are_quiet_and_define_expected_helpers_only():
    """All /app/lib/*.sh files must be quiet sourceable libraries defining expected helpers."""
    script = r"""
set +e
set +u
set +o pipefail
before="$(set +o)"
out="$(mktemp)"
err="$(mktemp)"
(
  source /app/lib/common.sh
  source /app/lib/compare-trees.sh
  source /app/lib/wait-sync.sh
  source /app/lib/write-status.sh
  for fn in ldap_admin wait_for_port context_csn_for_suffix trees_equivalent wait_for_sync write_replication_status; do
    type "$fn" >/dev/null 2>&1 || exit 32
  done
) >"$out" 2>"$err"
after="$(set +o)"
if [ "$before" != "$after" ]; then exit 30; fi
if [ -s "$out" ] || [ -s "$err" ]; then exit 31; fi
exit 0
"""
    result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_compare_trees_normalizes_multivalue_attribute_order_without_hiding_value_changes():
    """compare-trees equivalence must ignore multivalue order but detect value changes."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("compare_multivalue")
    group_dn = f"cn=mv-{token},ou=groups,{BASE_DN}"
    apply_provider_ldif(
        f"""dn: {group_dn}
changetype: add
objectClass: groupOfNames
cn: mv-{token}
member: uid=alice,ou=people,{BASE_DN}
member: uid=bob,ou=people,{BASE_DN}
"""
    )
    wait_for_sync()
    assert compare_trees_via_lib().returncode == 0
    apply_provider_ldif(
        f"""dn: {group_dn}
changetype: modify
replace: member
member: uid=bob,ou=people,{BASE_DN}
member: uid=alice,ou=people,{BASE_DN}
"""
    )
    wait_for_sync()
    assert compare_trees_via_lib().returncode == 0
    slapmodify_consumer_offline(
        f"""dn: {group_dn}
changetype: modify
replace: member
member: uid=bob,ou=people,{BASE_DN}
"""
    )
    assert compare_trees_via_lib().returncode != 0


def test_wait_sync_requires_tree_equivalence_not_context_csn_only(tmp_path):
    """wait-sync must not succeed on matching CSNs when normalized trees still differ."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("wait_sync_tree_equiv")
    apply_provider_ldif(
        f"""dn: cn=ws-{token},ou=groups,{BASE_DN}
changetype: add
objectClass: groupOfNames
cn: ws-{token}
member: uid=alice,ou=people,{BASE_DN}
"""
    )
    wait_for_sync()
    provider_csn = context_csn(PROVIDER_URI, BASE_DN)
    ghost_ldif = f"""dn: uid=ghostws-{token},ou=people,{BASE_DN}
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Ghost {token}
sn: {token}
uid: ghostws-{token}
mail: ghostws-{token}@example.com
"""
    slapadd_consumer_offline(ghost_ldif)
    if provider_csn:
        slapmodify_consumer_offline(
            f"dn: {BASE_DN}\n"
            "changetype: modify\n"
            f"replace: contextCSN\n"
            f"contextCSN: {provider_csn}\n"
        )
    assert not trees_equivalent()
    result = wait_sync_via_lib(timeout=8)
    assert result.returncode != 0


def test_dynamic_seeded_restore_matrix_mixes_delete_rename_verifier_suffix_and_status(tmp_path):
    """Combined restore scenario covers delete, rename, verifier suffix, and primary-only status."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("restore_matrix")
    uid = f"mx-{token}"
    person_dn = add_person(uid, description="matrix-user")
    verifier_dn = add_verifier_record(f"vmx-{token}")
    wait_for_base_sync(VERIFIER_BASE)
    backup = make_consumer_backup(tmp_path, name="matrix.tar")
    new_uid = f"mx2-{token}"
    apply_provider_ldif(
        f"""dn: {person_dn}
changetype: modrdn
newrdn: uid={new_uid}
deleteoldrdn: 1

dn: uid={new_uid},ou=people,{BASE_DN}
changetype: delete

dn: {verifier_dn}
changetype: modify
replace: description
description: matrix-verifier-mutated
"""
    )
    wait_for_sync()
    proc = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert proc.returncode == 0, proc.stderr
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid={new_uid})")
    assert not dn_exists(CONSUMER_URI, BASE_DN, f"(uid={uid})")
    wait_for_base_sync(VERIFIER_BASE)
    assert check_replica(STATUS_PATH).returncode == 0
    status = load_status(STATUS_PATH)
    assert status["provider_entry_count"] == entry_count(PROVIDER_URI, BASE_DN)
    assert status["equivalent"] is True
    stop_ldap()
    stale = STATUS_PATH.read_bytes() if STATUS_PATH.exists() else b""
    assert check_replica(STATUS_PATH).returncode != 0
    assert_no_stale_report(STATUS_PATH, stale)


def test_large_composed_restart_restore_acl_status_idempotency_family(tmp_path):
    """Combined scenario exercises restart, restore, ACL, status, backup immutability, and idempotency."""
    reset_consumer_data()
    wait_for_sync()
    token = deterministic_token("composed_family")
    person_dn = add_person(f"fam-{token}")
    wait_for_sync()
    backup = make_consumer_backup(tmp_path, name="family.tar")
    before_hash = sha256_file(backup)
    apply_provider_ldif(f"dn: {person_dn}\nchangetype: delete\n")
    wait_for_sync()
    stop_ldap()
    start_ldap()
    start_ldap()
    restore = run_cmd(["/app/bin/restore-consumer", str(backup)], check=False)
    assert restore.returncode == 0, restore.stderr
    assert sha256_file(backup) == before_hash
    wait_for_sync()
    assert trees_equivalent()
    primary_reader = ldapsearch_as(
        PROVIDER_URI, READER_DN, READER_PW, "-b", f"ou=people,{BASE_DN}", "(uid=bob)", "dn"
    )
    assert "dn:" in primary_reader
    accesslog_proc = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            PROVIDER_URI,
            "-D",
            READER_DN,
            "-w",
            READER_PW,
            "-b",
            "cn=accesslog",
            "(objectClass=*)",
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert accesslog_proc.returncode != 0 or "dn:" not in accesslog_proc.stdout
    first = check_replica(STATUS_PATH)
    second = check_replica(STATUS_PATH)
    assert first.returncode == 0 and second.returncode == 0
    status = load_status(STATUS_PATH)
    assert status["equivalent"] is True
    assert status["provider_entry_count"] == entry_count(PROVIDER_URI, BASE_DN)
    stop_ldap()
    start_ldap()
    wait_for_sync()
    assert process_count_for_slapd_role("provider") == 1
    assert process_count_for_slapd_role("consumer") == 1
