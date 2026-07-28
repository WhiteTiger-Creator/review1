"""Verifier for NFS export ACL daemon runtime state."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

CONFIG_PATH = Path("/app/config/exports.json")
JOURNAL_PATH = Path("/app/var/lib/nfs-acld/export.journal")
ACL_PATH = Path("/app/run/export_acls.json")
METRICS_PATH = Path("/app/run/export_metrics.json")
OVERLAY_PATH = Path("/app/config/profiles/nfs-east-ops.toml")
UNIT_PATH = Path("/app/systemd/nfs-export-acld.service")
PROTECTED = [
    Path("/app/config/exports.json"),
    Path("/app/docs/nfs-export-ops-policy.md"),
    Path("/app/governance/nfs-east-baseline.md"),
    Path("/app/systemd/nfs-export-acld.service"),
    Path("/app/var/lib/nfs-acld/export.journal"),
]


def load_json(path: Path):
    """Load a JSON document from disk."""
    with path.open() as f:
        return json.load(f)


def load_journal():
    """Load NFS export ACL journal events from the on-disk WAL."""
    ops = []
    with JOURNAL_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                ops.append(json.loads(line))
    return ops


def round_half_away(value: float, ndigits: int) -> float:
    """Round half away from zero to ndigits decimal places."""
    factor = 10**ndigits
    scaled = value * factor
    if scaled >= 0:
        return math.floor(scaled + 0.5) / factor
    return math.ceil(scaled - 0.5) / factor


def specificity(client_id: str) -> int:
    """Compute client specificity per the NFS export ops policy."""
    if re.search(r"[A-Za-z]", client_id):
        return 128
    if "/" in client_id:
        return int(client_id.rsplit("/", 1)[1])
    return 32


def simulate_ops():
    """Independently replay the journal under the NFS export ops policy."""
    cfg = load_json(CONFIG_PATH)
    max_clients = int(cfg["max_clients_per_export"])
    def_squash = cfg["default_squash"]
    def_anon_uid = int(cfg["default_anon_uid"])
    def_anon_gid = int(cfg["default_anon_gid"])
    def_access = cfg["default_access"]
    require_secure = bool(cfg["require_secure_ports"])
    eval_clock = int(cfg["evaluation_clock"])
    table_id = cfg["export_table_id"]

    exports = {}
    waitlist = []
    seen = set()
    applied = 0
    skipped_dup = 0

    def state_of(secure):
        if require_secure and not secure:
            return "insecure"
        return "active"

    def new_grant(client_id, access, squash, anon_uid, anon_gid, secure):
        if squash == "all_squash":
            anon_uid = def_anon_uid
            anon_gid = def_anon_gid
        return {
            "client_id": client_id,
            "access": access,
            "squash": squash,
            "anon_uid": anon_uid,
            "anon_gid": anon_gid,
            "secure": secure,
            "specificity": specificity(client_id),
            "state": state_of(secure),
        }

    def promote(export_path):
        idx = next((i for i, w in enumerate(waitlist) if w["export_path"] == export_path), None)
        if idx is None:
            return False
        entry = waitlist[idx]
        if export_path not in exports:
            waitlist.pop(idx)
            return True
        clients = exports[export_path]
        if len(clients) >= max_clients:
            return False
        if entry["client_id"] in clients:
            waitlist.pop(idx)
            return True
        clients[entry["client_id"]] = new_grant(
            entry["client_id"], def_access, def_squash, def_anon_uid, def_anon_gid, True
        )
        waitlist.pop(idx)
        return True

    for op in load_journal():
        oid = op["op_id"]
        if oid in seen:
            skipped_dup += 1
            continue
        seen.add(oid)
        applied += 1
        typ = op["type"]

        if typ == "create_export":
            path = op["export_path"]
            if path not in exports:
                exports[path] = {}
        elif typ == "grant":
            path = op["export_path"]
            if path not in exports:
                continue
            cid = op["client_id"]
            if cid in exports[path]:
                continue
            if len(exports[path]) >= max_clients:
                continue
            access = op.get("access", def_access)
            squash = op.get("squash", def_squash)
            anon_uid = op.get("anon_uid", def_anon_uid)
            anon_gid = op.get("anon_gid", def_anon_gid)
            secure = op.get("secure", True)
            exports[path][cid] = new_grant(cid, access, squash, anon_uid, anon_gid, secure)
        elif typ == "revoke":
            path = op["export_path"]
            cid = op["client_id"]
            if path not in exports or cid not in exports[path]:
                continue
            del exports[path][cid]
            promote(path)
        elif typ == "enqueue":
            path = op["export_path"]
            cid = op["client_id"]
            if any(w["export_path"] == path and w["client_id"] == cid for w in waitlist):
                continue
            waitlist.append({"export_path": path, "client_id": cid})
        elif typ == "set_squash":
            path = op["export_path"]
            cid = op["client_id"]
            if path not in exports or cid not in exports[path]:
                continue
            g = exports[path][cid]
            g["squash"] = op["squash"]
            if g["squash"] == "all_squash":
                g["anon_uid"] = def_anon_uid
                g["anon_gid"] = def_anon_gid
            g["state"] = state_of(g["secure"])
        elif typ == "set_access":
            path = op["export_path"]
            cid = op["client_id"]
            if path not in exports or cid not in exports[path]:
                continue
            exports[path][cid]["access"] = op["access"]
        elif typ == "destroy_export":
            exports.pop(op["export_path"], None)
        elif typ == "reexport_pass":
            for path in sorted(exports):
                while True:
                    if len(exports[path]) >= max_clients:
                        break
                    if not any(w["export_path"] == path for w in waitlist):
                        break
                    if not promote(path):
                        break

    export_list = []
    for path in sorted(exports):
        clients = list(exports[path].values())
        clients.sort(key=lambda c: (-c["specificity"], c["client_id"]))
        export_list.append({"export_path": path, "clients": clients})

    grant_count = sum(len(e["clients"]) for e in export_list)
    insecure = sum(1 for e in export_list for c in e["clients"] if c["state"] == "insecure")
    over_cap = sum(1 for e in export_list if len(e["clients"]) > max_clients)
    export_count = len(export_list)
    wait_depth = len(waitlist)
    util = 0.0
    if export_count > 0:
        util = round_half_away(grant_count / (export_count * max_clients), 4)
    penalties = insecure * 20 + over_cap * 25 + wait_depth * 2
    compliance = max(0.0, round_half_away(100 - penalties, 2))

    acls = {
        "evaluation_clock": eval_clock,
        "export_table_id": table_id,
        "max_clients_per_export": max_clients,
        "exports": export_list,
        "waitlist": waitlist,
    }
    metrics = {
        "export_count": export_count,
        "client_grant_count": grant_count,
        "waitlist_depth": wait_depth,
        "insecure_grant_count": insecure,
        "over_capacity_exports": over_cap,
        "journal_applied": applied,
        "journal_skipped_dup": skipped_dup,
        "slot_utilization_ratio": util,
        "export_compliance": compliance,
    }
    return acls, metrics


def test_runtime_acl_file_exists():
    """Runtime export ACL inventory file must exist after oneshot convergence."""
    assert ACL_PATH.is_file()


def test_runtime_metrics_file_exists():
    """Runtime export metrics file must exist after oneshot convergence."""
    assert METRICS_PATH.is_file()


def test_systemd_unit_present():
    """Systemd oneshot unit for NFS export ACL reconciliation must be present."""
    assert UNIT_PATH.is_file()
    text = UNIT_PATH.read_text()
    assert "Type=oneshot" in text
    assert "start-nfs-acld.sh" in text


def test_protected_inputs_unchanged():
    """Protected config, docs, governance, unit, and journal trees must remain unchanged."""
    assert CONFIG_PATH.is_file()
    assert OVERLAY_PATH.is_file()
    cfg = load_json(CONFIG_PATH)
    assert cfg["max_clients_per_export"] == 3
    assert cfg["default_squash"] == "root_squash"
    assert cfg["default_anon_uid"] == 65534
    overlay = OVERLAY_PATH.read_text()
    assert "max_clients_per_export = 5" in overlay
    journal = JOURNAL_PATH.read_text()
    assert '"op_id":"op01"' in journal
    policy = Path("/app/docs/nfs-export-ops-policy.md").read_text()
    assert "max_clients_per_export" in policy


def test_acl_schema_fields():
    """export_acls.json must expose the schema fields required by the ops policy."""
    acls = load_json(ACL_PATH)
    for key in (
        "evaluation_clock",
        "export_table_id",
        "max_clients_per_export",
        "exports",
        "waitlist",
    ):
        assert key in acls
    assert isinstance(acls["exports"], list)
    assert isinstance(acls["waitlist"], list)
    for exp in acls["exports"]:
        assert "export_path" in exp
        assert "clients" in exp
        for c in exp["clients"]:
            for field in (
                "client_id",
                "access",
                "squash",
                "anon_uid",
                "anon_gid",
                "secure",
                "specificity",
                "state",
            ):
                assert field in c


def test_metrics_schema_fields():
    """export_metrics.json must expose the metric fields required by the ops policy."""
    metrics = load_json(METRICS_PATH)
    for key in (
        "export_count",
        "client_grant_count",
        "waitlist_depth",
        "insecure_grant_count",
        "over_capacity_exports",
        "journal_applied",
        "journal_skipped_dup",
        "slot_utilization_ratio",
        "export_compliance",
    ):
        assert key in metrics


def test_matches_independent_replay_acls():
    """Persisted ACL inventory must match an independent policy-faithful journal replay."""
    expected, _ = simulate_ops()
    actual = load_json(ACL_PATH)
    assert actual == expected


def test_matches_independent_replay_metrics():
    """Persisted metrics must match an independent policy-faithful journal replay."""
    _, expected = simulate_ops()
    actual = load_json(METRICS_PATH)
    assert actual == expected


def test_base_max_clients_authoritative():
    """Persisted max_clients_per_export must equal base configuration, not overlay."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    assert acls["max_clients_per_export"] == cfg["max_clients_per_export"]
    assert acls["max_clients_per_export"] != 5
    assert acls["max_clients_per_export"] != 8


def test_export_table_id_and_clock():
    """Runtime ACL document must retain base export_table_id and evaluation_clock."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    assert acls["export_table_id"] == cfg["export_table_id"]
    assert acls["evaluation_clock"] == cfg["evaluation_clock"]


def test_exports_sorted_by_path():
    """Exports must be sorted by export_path ascending."""
    acls = load_json(ACL_PATH)
    paths = [e["export_path"] for e in acls["exports"]]
    assert paths == sorted(paths)


def test_clients_sorted_by_specificity_desc():
    """Clients within an export must sort by specificity descending, then client_id ascending."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        clients = exp["clients"]
        keyed = [(c["specificity"], c["client_id"]) for c in clients]
        expected = sorted(keyed, key=lambda t: (-t[0], t[1]))
        assert keyed == expected


def test_hostname_specificity_is_128():
    """Hostname clients must receive specificity 128."""
    acls = load_json(ACL_PATH)
    found = False
    for exp in acls["exports"]:
        for c in exp["clients"]:
            if re.search(r"[A-Za-z]", c["client_id"]):
                assert c["specificity"] == 128
                found = True
    assert found


def test_cidr_specificity_uses_prefix():
    """IPv4 CIDR clients must use the prefix length as specificity."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        for c in exp["clients"]:
            if "/" in c["client_id"] and not re.search(r"[A-Za-z]", c["client_id"]):
                assert c["specificity"] == int(c["client_id"].rsplit("/", 1)[1])


def test_bare_ipv4_specificity_is_32():
    """Bare IPv4 clients must receive specificity 32."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        for c in exp["clients"]:
            cid = c["client_id"]
            if "/" not in cid and not re.search(r"[A-Za-z]", cid):
                assert c["specificity"] == 32


def test_no_export_exceeds_base_max_clients():
    """No export may hold more grants than base max_clients_per_export."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    max_c = cfg["max_clients_per_export"]
    for exp in acls["exports"]:
        assert len(exp["clients"]) <= max_c


def test_duplicate_op_id_skipped():
    """Duplicate journal op_id lines must be skipped and counted."""
    metrics = load_json(METRICS_PATH)
    assert metrics["journal_skipped_dup"] == 1
    assert metrics["journal_applied"] == 30


def test_waitlist_is_fifo_pairs():
    """Remaining waitlist must be FIFO export_path/client_id pairs from independent replay."""
    expected, _ = simulate_ops()
    actual = load_json(ACL_PATH)
    assert actual["waitlist"] == expected["waitlist"]
    assert actual["waitlist"][0]["export_path"] == "/srv/share/alpha"
    assert actual["waitlist"][0]["client_id"] == "lab-client"


def test_all_squash_forces_base_anon_mapping():
    """all_squash grants must force anon UID/GID to base defaults, not zero."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    found = False
    for exp in acls["exports"]:
        for c in exp["clients"]:
            if c["squash"] == "all_squash":
                assert c["anon_uid"] == cfg["default_anon_uid"]
                assert c["anon_gid"] == cfg["default_anon_gid"]
                found = True
    assert found


def test_insecure_grant_revoked_not_present():
    """The insecure beta grant that was revoked must not remain in inventory."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        if exp["export_path"] == "/srv/share/beta":
            ids = {c["client_id"] for c in exp["clients"]}
            assert "192.168.1.50" not in ids


def test_promoted_clients_use_base_defaults():
    """Waitlist-promoted clients must receive base access/squash/anon/secure defaults."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    promoted = {
        "/srv/share/alpha": "10.9.9.9",
        "/srv/share/beta": "192.168.2.0/24",
        "/srv/share/gamma": "batch-runner",
    }
    for path, cid in promoted.items():
        exp = next(e for e in acls["exports"] if e["export_path"] == path)
        grant = next(c for c in exp["clients"] if c["client_id"] == cid)
        assert grant["access"] == cfg["default_access"]
        assert grant["squash"] == cfg["default_squash"]
        assert grant["anon_uid"] == cfg["default_anon_uid"]
        assert grant["anon_gid"] == cfg["default_anon_gid"]
        assert grant["secure"] is True
        assert grant["state"] == "active"


def test_destroy_does_not_clear_unrelated_waitlist():
    """Destroying an export must not remove waitlist entries for other paths, and delta wait remains."""
    acls = load_json(ACL_PATH)
    assert any(
        w["export_path"] == "/srv/share/delta" and w["client_id"] == "10.10.10.10"
        for w in acls["waitlist"]
    )
    paths = {e["export_path"] for e in acls["exports"]}
    assert "/srv/share/delta" not in paths


def test_alpha_client_set_after_revoke_promote():
    """Alpha must contain the post-revoke promoted client set from policy replay."""
    acls = load_json(ACL_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    ids = {c["client_id"] for c in alpha["clients"]}
    assert ids == {"edge-gateway", "10.1.2.0/24", "10.9.9.9"}
    assert "10.0.0.0/8" not in ids


def test_gamma_batch_runner_promoted_on_reexport():
    """Gamma must include batch-runner promoted during reexport_pass."""
    acls = load_json(ACL_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    ids = {c["client_id"] for c in gamma["clients"]}
    assert "batch-runner" in ids
    assert "172.16.0.0/12" not in ids


def test_slot_utilization_half_away_rounding():
    """slot_utilization_ratio must use half-away-from-zero rounding to 4 decimals."""
    metrics = load_json(METRICS_PATH)
    _, expected = simulate_ops()
    assert metrics["slot_utilization_ratio"] == expected["slot_utilization_ratio"]
    assert metrics["slot_utilization_ratio"] == 0.8889


def test_export_compliance_formula():
    """export_compliance must equal max(0, round(100 - penalties, 2)) per policy weights."""
    metrics = load_json(METRICS_PATH)
    _, expected = simulate_ops()
    assert metrics["export_compliance"] == expected["export_compliance"]
    assert metrics["export_compliance"] == 94.0


def test_metrics_counts_consistent_with_acls():
    """Metric counters must be consistent with the persisted ACL inventory."""
    acls = load_json(ACL_PATH)
    metrics = load_json(METRICS_PATH)
    assert metrics["export_count"] == len(acls["exports"])
    assert metrics["client_grant_count"] == sum(len(e["clients"]) for e in acls["exports"])
    assert metrics["waitlist_depth"] == len(acls["waitlist"])
    assert metrics["insecure_grant_count"] == sum(
        1 for e in acls["exports"] for c in e["clients"] if c["state"] == "insecure"
    )
    assert metrics["over_capacity_exports"] == 0


def test_grant_does_not_rewrite_existing_options():
    """Re-granting an existing client must leave original options intact."""
    acls = load_json(ACL_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    edge = next(c for c in alpha["clients"] if c["client_id"] == "edge-gateway")
    assert edge["access"] == "rw"
    assert edge["squash"] == "all_squash"


def test_beta_ops_host_all_squash_anon():
    """Beta ops-host set_squash to all_squash must use base anon mapping."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    ops = next(c for c in beta["clients"] if c["client_id"] == "ops-host")
    assert ops["squash"] == "all_squash"
    assert ops["anon_uid"] == cfg["default_anon_uid"]
    assert ops["anon_gid"] == cfg["default_anon_gid"]
    assert ops["access"] == "ro"


def test_beta_access_update_persists():
    """set_access on beta CIDR client must persist rw access."""
    acls = load_json(ACL_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    cidr = next(c for c in beta["clients"] if c["client_id"] == "192.168.0.0/16")
    assert cidr["access"] == "rw"


def test_idempotent_replay_counters():
    """Journal applied/skipped counters must reflect first-seen op_id semantics."""
    metrics = load_json(METRICS_PATH)
    lines = [ln for ln in JOURNAL_PATH.read_text().splitlines() if ln.strip()]
    assert len(lines) == 31
    assert metrics["journal_applied"] + metrics["journal_skipped_dup"] == len(lines)


def test_states_only_active_or_insecure():
    """Grant state labels must be exactly active or insecure."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        for c in exp["clients"]:
            assert c["state"] in {"active", "insecure"}


def test_no_insecure_grants_remain():
    """After revoke of the insecure grant, insecure_grant_count must be zero."""
    metrics = load_json(METRICS_PATH)
    assert metrics["insecure_grant_count"] == 0


def test_overlay_values_not_used_for_defaults_on_promote():
    """Promoted grants must not inherit overlay no_root_squash or rw defaults."""
    acls = load_json(ACL_PATH)
    for path, cid in (
        ("/srv/share/alpha", "10.9.9.9"),
        ("/srv/share/beta", "192.168.2.0/24"),
        ("/srv/share/gamma", "batch-runner"),
    ):
        exp = next(e for e in acls["exports"] if e["export_path"] == path)
        grant = next(c for c in exp["clients"] if c["client_id"] == cid)
        assert grant["squash"] != "no_root_squash"
        assert grant["access"] == "ro"
        assert grant["anon_uid"] != 0


def test_export_count_metric_is_three():
    """export_count must equal the number of surviving export paths."""
    metrics = load_json(METRICS_PATH)
    assert metrics["export_count"] == 3


def test_client_grant_count_metric_is_eight():
    """client_grant_count must equal total grants across all exports."""
    metrics = load_json(METRICS_PATH)
    assert metrics["client_grant_count"] == 8


def test_waitlist_depth_metric_is_three():
    """waitlist_depth must equal remaining FIFO waitlist length."""
    metrics = load_json(METRICS_PATH)
    assert metrics["waitlist_depth"] == 3


def test_alpha_has_exactly_three_clients():
    """Alpha must hold exactly base max_clients_per_export grants."""
    acls = load_json(ACL_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    assert len(alpha["clients"]) == 3


def test_beta_has_exactly_three_clients():
    """Beta must hold exactly base max_clients_per_export grants."""
    acls = load_json(ACL_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    assert len(beta["clients"]) == 3


def test_gamma_has_exactly_two_clients():
    """Gamma must hold exactly two grants after revoke and promotion."""
    acls = load_json(ACL_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    assert len(gamma["clients"]) == 2


def test_alpha_clients_ordered_by_specificity():
    """Alpha clients must appear in specificity-desc then client_id-asc order."""
    acls = load_json(ACL_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    ids = [c["client_id"] for c in alpha["clients"]]
    assert ids == ["edge-gateway", "10.9.9.9", "10.1.2.0/24"]


def test_beta_clients_ordered_by_specificity():
    """Beta clients must appear in specificity-desc then client_id-asc order."""
    acls = load_json(ACL_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    ids = [c["client_id"] for c in beta["clients"]]
    assert ids == ["ops-host", "192.168.2.0/24", "192.168.0.0/16"]


def test_gamma_clients_ordered_by_specificity():
    """Gamma clients must appear in specificity-desc then client_id-asc order."""
    acls = load_json(ACL_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    ids = [c["client_id"] for c in gamma["clients"]]
    assert ids == ["batch-runner", "172.16.5.5"]


def test_waitlist_second_entry_is_alpha_cidr():
    """Second waitlist entry must be the later alpha CIDR reservation."""
    acls = load_json(ACL_PATH)
    assert acls["waitlist"][1]["export_path"] == "/srv/share/alpha"
    assert acls["waitlist"][1]["client_id"] == "10.2.0.0/16"


def test_waitlist_third_entry_is_delta_client():
    """Third waitlist entry must remain the destroyed-export delta reservation."""
    acls = load_json(ACL_PATH)
    assert acls["waitlist"][2]["export_path"] == "/srv/share/delta"
    assert acls["waitlist"][2]["client_id"] == "10.10.10.10"


def test_gamma_all_squash_forces_base_anon():
    """Gamma all_squash grant must force base anon UID/GID despite grant payload zeros."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    grant = next(c for c in gamma["clients"] if c["client_id"] == "172.16.5.5")
    assert grant["squash"] == "all_squash"
    assert grant["anon_uid"] == cfg["default_anon_uid"]
    assert grant["anon_gid"] == cfg["default_anon_gid"]
    assert grant["access"] == "rw"


def test_ops_host_omitted_access_uses_base_default():
    """Grant omitting access must use base default_access for ops-host."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    ops = next(c for c in beta["clients"] if c["client_id"] == "ops-host")
    assert ops["access"] == cfg["default_access"]


def test_beta_promoted_cidr_specificity_is_24():
    """Promoted beta CIDR client must use prefix length 24 as specificity."""
    acls = load_json(ACL_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    grant = next(c for c in beta["clients"] if c["client_id"] == "192.168.2.0/24")
    assert grant["specificity"] == 24


def test_alpha_promoted_bare_ip_specificity_is_32():
    """Promoted alpha bare IPv4 client must use specificity 32."""
    acls = load_json(ACL_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    grant = next(c for c in alpha["clients"] if c["client_id"] == "10.9.9.9")
    assert grant["specificity"] == 32


def test_batch_runner_specificity_is_128():
    """Hostname batch-runner must carry specificity 128."""
    acls = load_json(ACL_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    grant = next(c for c in gamma["clients"] if c["client_id"] == "batch-runner")
    assert grant["specificity"] == 128


def test_duplicate_enqueue_does_not_duplicate_lab_client():
    """Duplicate enqueue of lab-client must leave a single waitlist pair."""
    acls = load_json(ACL_PATH)
    matches = [
        w
        for w in acls["waitlist"]
        if w["export_path"] == "/srv/share/alpha" and w["client_id"] == "lab-client"
    ]
    assert len(matches) == 1


def test_capacity_rejected_client_absent_until_promote():
    """Over-capacity direct grant of 10.9.9.9 must not leave a non-promoted grant shape."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    grant = next(c for c in alpha["clients"] if c["client_id"] == "10.9.9.9")
    assert grant["access"] == cfg["default_access"]
    assert grant["squash"] == cfg["default_squash"]


def test_skipped_dup_payload_client_absent():
    """Duplicate op_id payload client must not appear in any export inventory."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        ids = {c["client_id"] for c in exp["clients"]}
        assert "should-skip-dup" not in ids


def test_capacity_blocked_gamma_client_absent():
    """Grant that would exceed gamma capacity must not create missing-export-client."""
    acls = load_json(ACL_PATH)
    gamma = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/gamma")
    ids = {c["client_id"] for c in gamma["clients"]}
    assert "missing-export-client" not in ids


def test_over_capacity_exports_metric_zero():
    """over_capacity_exports must be zero when all exports respect base max clients."""
    metrics = load_json(METRICS_PATH)
    assert metrics["over_capacity_exports"] == 0


def test_evaluation_clock_matches_base_config_value():
    """evaluation_clock must equal the base configuration integer clock."""
    acls = load_json(ACL_PATH)
    assert acls["evaluation_clock"] == 50000


def test_export_table_id_matches_base_config_value():
    """export_table_id must equal the base configuration table identifier."""
    acls = load_json(ACL_PATH)
    assert acls["export_table_id"] == "nfs-east-01"


def test_all_remaining_grants_are_secure():
    """Every remaining grant must have secure=true after insecure revoke."""
    acls = load_json(ACL_PATH)
    for exp in acls["exports"]:
        for c in exp["clients"]:
            assert c["secure"] is True
            assert c["state"] == "active"


def test_only_three_export_paths_remain():
    """Runtime inventory must contain exactly alpha, beta, and gamma exports."""
    acls = load_json(ACL_PATH)
    paths = [e["export_path"] for e in acls["exports"]]
    assert paths == ["/srv/share/alpha", "/srv/share/beta", "/srv/share/gamma"]


def test_alpha_edge_gateway_anon_after_set_squash():
    """Alpha edge-gateway set_squash to all_squash must force base anon mapping."""
    acls = load_json(ACL_PATH)
    cfg = load_json(CONFIG_PATH)
    alpha = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/alpha")
    edge = next(c for c in alpha["clients"] if c["client_id"] == "edge-gateway")
    assert edge["squash"] == "all_squash"
    assert edge["anon_uid"] == cfg["default_anon_uid"]
    assert edge["anon_gid"] == cfg["default_anon_gid"]
    assert edge["access"] == "rw"


def test_beta_slash16_specificity_is_16():
    """Beta 192.168.0.0/16 client must use specificity 16."""
    acls = load_json(ACL_PATH)
    beta = next(e for e in acls["exports"] if e["export_path"] == "/srv/share/beta")
    grant = next(c for c in beta["clients"] if c["client_id"] == "192.168.0.0/16")
    assert grant["specificity"] == 16


def test_waitlist_entries_are_path_client_pairs():
    """Each waitlist entry must expose exactly export_path and client_id keys."""
    acls = load_json(ACL_PATH)
    assert len(acls["waitlist"]) == 3
    for entry in acls["waitlist"]:
        assert set(entry.keys()) == {"export_path", "client_id"}


def test_compliance_reflects_waitlist_penalties_only():
    """With no insecure or over-capacity exports, compliance must be 100 - 2*waitlist_depth."""
    metrics = load_json(METRICS_PATH)
    assert metrics["insecure_grant_count"] == 0
    assert metrics["over_capacity_exports"] == 0
    assert metrics["export_compliance"] == round_half_away(100 - metrics["waitlist_depth"] * 2, 2)


def test_independent_replay_waitlist_length_matches_metrics():
    """Independent policy replay waitlist length must equal waitlist_depth metric."""
    expected, metrics_expected = simulate_ops()
    actual_metrics = load_json(METRICS_PATH)
    assert len(expected["waitlist"]) == actual_metrics["waitlist_depth"]
    assert actual_metrics["waitlist_depth"] == metrics_expected["waitlist_depth"]
