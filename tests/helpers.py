"""Verifier helpers for OpenLDAP delta-syncrepl replication."""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

PROVIDER_URI = "ldap://127.0.0.1:1389"
CONSUMER_URI = "ldap://127.0.0.1:2389"
ADMIN_DN = "cn=admin,dc=example,dc=com"
ADMIN_PW = "adminsecret"
REPLICATOR_DN = "cn=replicator,dc=example,dc=com"
REPLICATOR_PW = "replicsecret"
READER_DN = "uid=reader,ou=people,dc=example,dc=com"
READER_PW = "readersecret"
BASE_DN = "dc=example,dc=com"
VERIFIER_BASE = "dc=verifier,dc=internal"
BACKUP = Path("/app/backups/consumer-state.tar")
STATUS_PATH = Path("/output/replication-status.json")
LDAP_RUNTIME = Path("/app/ldap/runtime")

START_LDAP = Path("/app/bin/start-ldap")
STOP_LDAP = Path("/app/bin/stop-ldap")
CHECK_REPLICA = Path("/app/bin/check-replica")
RESTORE_CONSUMER = Path("/app/bin/restore-consumer")


def run_cmd(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def stop_ldap() -> None:
    run_cmd([str(STOP_LDAP)], check=False)


def start_ldap() -> None:
    run_cmd([str(START_LDAP)])


def ldapsearch_as(
    uri: str,
    bind_dn: str,
    password: str,
    *args: str,
    check: bool = True,
) -> str:
    cmd = [
        "ldapsearch",
        "-x",
        "-LLL",
        "-H",
        uri,
        "-D",
        bind_dn,
        "-w",
        password,
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def stop_consumer_only() -> None:
    pidfile = LDAP_RUNTIME / "consumer.pid"
    if not pidfile.exists():
        return
    pid = pidfile.read_text().strip()
    if pid:
        subprocess.run(["kill", pid], check=False)
        for _ in range(10):
            if subprocess.run(["kill", "-0", pid], check=False).returncode != 0:
                break
            time.sleep(0.2)
        subprocess.run(["kill", "-9", pid], check=False)
    pidfile.unlink(missing_ok=True)
    argsfile = LDAP_RUNTIME / "consumer.args"
    argsfile.unlink(missing_ok=True)


def slapmodify_consumer_offline(ldif: str) -> None:
    stop_consumer_only()
    proc = subprocess.run(
        ["slapmodify", "-f", "/app/ldap/consumer/slapd.conf", "-b", BASE_DN],
        input=ldif,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    start_ldap()


def slapadd_consumer_offline(ldif: str) -> None:
    stop_consumer_only()
    proc = subprocess.run(
        ["slapadd", "-f", "/app/ldap/consumer/slapd.conf"],
        input=ldif,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    start_ldap()


def ldapsearch(
    uri: str,
    bind_dn: str,
    password: str,
    *args: str,
) -> str:
    return ldapsearch_as(uri, bind_dn, password, *args)


def ldapmodify_as(bind_dn: str, password: str, ldif: str, *, uri: str = PROVIDER_URI) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ldapmodify", "-x", "-H", uri, "-D", bind_dn, "-w", password],
        input=ldif,
        capture_output=True,
        text=True,
        check=False,
    )


def wait_until(predicate, timeout: float = 45.0, interval: float = 0.25) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(interval)
    if last_error is not None:
        raise AssertionError(f"condition not met: {last_error}")
    raise AssertionError("condition not met before timeout")


def _parse_ldap_entries(output: str) -> list[list[str]]:
    entries: list[list[str]] = []
    current: list[str] = []
    for line in output.splitlines():
        if line.startswith("dn: "):
            if current:
                entries.append(current)
            current = [line]
        elif line and current:
            current.append(line)
    if current:
        entries.append(current)
    return entries


def normalized_tree(uri: str, base: str) -> list[str]:
    output = ldapsearch(
        uri,
        ADMIN_DN,
        ADMIN_PW,
        "-b",
        base,
        "(objectClass=*)",
        "dn",
        "objectClass",
        "cn",
        "uid",
        "mail",
        "sn",
        "description",
        "member",
    )
    normalized_entries: list[str] = []
    for entry_lines in _parse_ldap_entries(output):
        dn_line = entry_lines[0]
        attrs = sorted(entry_lines[1:])
        normalized_entries.append("\n".join([dn_line, *attrs]))
    return sorted(normalized_entries)


def trees_equivalent_for_base(base: str) -> bool:
    return normalized_tree(PROVIDER_URI, base) == normalized_tree(CONSUMER_URI, base)


def trees_equivalent() -> bool:
    return trees_equivalent_for_base(BASE_DN)


def wait_for_base_sync(base: str, timeout: float = 45.0) -> None:
    wait_until(lambda: trees_equivalent_for_base(base), timeout=timeout)


def wait_for_sync() -> None:
    wait_for_base_sync(BASE_DN)


def context_csn(uri: str, base: str) -> str:
    output = ldapsearch(uri, ADMIN_DN, ADMIN_PW, "-s", "base", "-b", base, "(objectClass=*)", "contextCSN")
    for line in output.splitlines():
        if line.startswith("contextCSN: "):
            return line.split(":", 1)[1].strip()
    return ""


def entry_count(uri: str, base: str) -> int:
    output = ldapsearch(uri, ADMIN_DN, ADMIN_PW, "-b", base, "(objectClass=*)", "dn")
    return sum(1 for line in output.splitlines() if line.startswith("dn: "))


def apply_provider_ldif(ldif: str) -> None:
    proc = ldapmodify_as(ADMIN_DN, ADMIN_PW, ldif)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def check_replica(report: Path = STATUS_PATH) -> subprocess.CompletedProcess[str]:
    return run_cmd([str(CHECK_REPLICA), "--report", str(report)], check=False)


def load_status(path: Path = STATUS_PATH) -> dict:
    return json.loads(path.read_text())


def reset_consumer_data() -> None:
    stop_ldap()
    for sub in ("data", "verifier-data"):
        target = Path(f"/app/ldap/consumer/{sub}")
        if target.exists():
            for child in target.iterdir():
                if child.is_dir():
                    subprocess.run(["rm", "-rf", str(child)], check=False)
                else:
                    child.unlink(missing_ok=True)
    start_ldap()
    wait_for_sync()


def deterministic_token(test_name: str, *, nbytes: int = 4) -> str:
    seed = int(hashlib.sha256(test_name.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    return "".join(rng.choice("0123456789abcdef") for _ in range(nbytes * 2))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dn_exists(uri: str, base: str, ldap_filter: str) -> bool:
    proc = subprocess.run(
        [
            "ldapsearch",
            "-x",
            "-LLL",
            "-H",
            uri,
            "-D",
            ADMIN_DN,
            "-w",
            ADMIN_PW,
            "-b",
            base,
            ldap_filter,
            "dn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False
    return any(line.startswith("dn: ") for line in proc.stdout.splitlines())


def assert_no_stale_report(path: Path, previous_bytes: bytes) -> None:
    if not path.exists():
        return
    current = path.read_bytes()
    if current == previous_bytes:
        raise AssertionError("stale success report was reused unchanged after failure")


def process_count_for_slapd_role(role: str) -> int:
    conf = f"/app/ldap/{role}/slapd.conf"
    proc = subprocess.run(
        ["pgrep", "-f", f"slapd -f {conf}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def read_pidfile(role: str) -> int | None:
    pidfile = LDAP_RUNTIME / f"{role}.pid"
    if not pidfile.exists():
        return None
    try:
        return int(pidfile.read_text().strip())
    except ValueError:
        return None


def consumer_context_csn_offline() -> str:
    proc = subprocess.run(
        ["slapcat", "-f", "/app/ldap/consumer/slapd.conf", "-b", BASE_DN, "-s", "base"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("contextCSN:"):
            return line.split(":", 1)[1].strip()
    return ""


def make_consumer_backup(
    tmp_path: Path,
    *,
    include_cookie: bool = True,
    cookie_override: str | None = None,
    include_verifier: bool = True,
    name: str = "backup.tar",
) -> Path:
    archive = tmp_path / name
    staging = tmp_path / f"staging-{name}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    stop_consumer_only()
    shutil.copytree("/app/ldap/consumer/data", staging / "data")
    if include_verifier:
        shutil.copytree("/app/ldap/consumer/verifier-data", staging / "verifier-data")
    cookie = cookie_override
    if include_cookie:
        meta = staging / "meta"
        meta.mkdir()
        if cookie is None:
            cookie = consumer_context_csn_offline()
        (meta / "context-csn").write_text(f"{cookie}\n")
    start_ldap()
    wait_for_base_sync(BASE_DN, timeout=20.0)
    with tarfile.open(archive, "w") as tar:
        for item in ("data", "verifier-data", "meta"):
            item_path = staging / item
            if item_path.exists():
                tar.add(item_path, arcname=item)
    shutil.rmtree(staging)
    return archive


def write_temp_archive_from_live_consumer(tmp_path: Path, name: str = "live-backup.tar") -> Path:
    return make_consumer_backup(tmp_path, include_cookie=True, include_verifier=True, name=name)


def compare_trees_via_lib(base: str = BASE_DN) -> subprocess.CompletedProcess[str]:
    script = f"""
source /app/lib/common.sh
source /app/lib/compare-trees.sh
if trees_equivalent_for_base "{base}"; then exit 0; else exit 1; fi
"""
    return subprocess.run(["bash", "--noprofile", "--norc", "-c", script], capture_output=True, text=True, check=False)


def wait_sync_via_lib(timeout: int = 12) -> subprocess.CompletedProcess[str]:
    script = f"""
source /app/lib/common.sh
source /app/lib/wait-sync.sh
wait_for_sync {timeout} 0.25
"""
    return subprocess.run(["bash", "--noprofile", "--norc", "-c", script], capture_output=True, text=True, check=False)


def accesslog_has_csn(csn: str) -> int:
    proc = subprocess.run(
        ["/app/lib/accesslog-has-csn.sh", csn],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode


def accesslog_search_as_replicator(ldap_filter: str, *attrs: str) -> str:
    attr_args: list[str] = []
    for attr in attrs or ("dn", "reqDN", "reqMod", "entryCSN"):
        attr_args.extend([attr])
    return ldapsearch_as(
        PROVIDER_URI,
        REPLICATOR_DN,
        REPLICATOR_PW,
        "-b",
        "cn=accesslog",
        ldap_filter,
        *attr_args,
    )


def server_id_for_role(role: str) -> str:
    conf = Path(f"/app/ldap/{role}/slapd.conf")
    if not conf.exists():
        return ""
    for line in conf.read_text().splitlines():
        if line.startswith("serverID "):
            return line.split(None, 1)[1].strip()
    return ""


def remove_generated_slapd_confs() -> None:
    for role in ("provider", "consumer"):
        conf = Path(f"/app/ldap/{role}/slapd.conf")
        if conf.exists():
            conf.unlink()


def add_person(uid: str, *, description: str = "generated person") -> str:
    apply_provider_ldif(
        f"""dn: uid={uid},ou=people,{BASE_DN}
changetype: add
objectClass: inetOrgPerson
cn: Person {uid}
sn: {uid}
uid: {uid}
mail: {uid}@example.com
description: {description}
"""
    )
    return f"uid={uid},ou=people,{BASE_DN}"


def add_group_with_member(cn: str, member_dn: str) -> str:
    apply_provider_ldif(
        f"""dn: cn={cn},ou=groups,{BASE_DN}
changetype: add
objectClass: groupOfNames
cn: {cn}
member: {member_dn}
"""
    )
    return f"cn={cn},ou=groups,{BASE_DN}"


def add_verifier_record(uid: str) -> str:
    apply_provider_ldif(
        f"""dn: uid={uid},ou=records,{VERIFIER_BASE}
changetype: add
objectClass: inetOrgPerson
cn: Record {uid}
sn: {uid}
uid: {uid}
description: verifier suffix record
"""
    )
    return f"uid={uid},ou=records,{VERIFIER_BASE}"


def parse_accesslog_fields(output: str) -> list[dict[str, list[str]]]:
    entries: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    for line in output.splitlines():
        if line.startswith("dn: "):
            if current:
                entries.append(current)
            current = {"dn": [line.split(":", 1)[1].strip()]}
        elif ": " in line and current:
            key, value = line.split(": ", 1)
            current.setdefault(key, []).append(value.strip())
    if current:
        entries.append(current)
    return entries


def csn_from_accesslog_output(output: str) -> set[str]:
    found: set[str] = set()
    for entry in parse_accesslog_fields(output):
        for key in ("entryCSN", "reqMod"):
            for value in entry.get(key, []):
                for match in re.findall(r"\d{14}\.\d{6}Z#[0-9a-f]+#[0-9]+", value):
                    found.add(match)
    return found


def ensure_verifier_suite_baseline() -> None:
    """Reset consumer state from the live provider before the verifier suite runs."""
    stop_ldap()
    reset_consumer_data()
    start_ldap()
    for uid in ("bob", "carol"):
        if not dn_exists(PROVIDER_URI, BASE_DN, f"(uid={uid})"):
            raise RuntimeError(
                f"provider primary seed entry uid={uid} is missing before verifier execution"
            )


def establish_primary_suffix_lag_with_synced_verifier(token: str) -> str:
    """Create a consumer-only primary divergence while verifier suffix stays equivalent."""
    verifier_dn = add_verifier_record(f"plag-{token}")
    wait_for_base_sync(VERIFIER_BASE)
    ghost_uid = f"plag-ghost-{token}"
    slapadd_consumer_offline(
        f"""dn: uid={ghost_uid},ou=people,{BASE_DN}
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Primary Lag Ghost {token}
sn: {token}
uid: {ghost_uid}
mail: {ghost_uid}@example.com
"""
    )
    if not dn_exists(CONSUMER_URI, BASE_DN, f"(uid={ghost_uid})"):
        raise AssertionError("consumer-only primary lag entry was not present after offline injection")
    if dn_exists(PROVIDER_URI, BASE_DN, f"(uid={ghost_uid})"):
        raise AssertionError("primary lag setup must exist only on the consumer")
    if not trees_equivalent_for_base(VERIFIER_BASE):
        raise AssertionError("verifier suffix must remain equivalent before primary lag check")
    if trees_equivalent_for_base(BASE_DN):
        raise AssertionError("primary suffix must be divergent before primary lag check")
    return verifier_dn
