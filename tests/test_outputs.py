import hashlib
import json
import shutil
import subprocess
from pathlib import Path

APP = Path("/app")
IRC = APP / "environment/irc"
STATE = IRC / "state"
FIX = IRC / "fixtures"
OUT = APP / "output"
STATUS = OUT / "status.json"
EVAL = OUT / "eval_binding.json"
TESTS = Path("/tests")
THREAT_POLICY = TESTS / "data" / "eval_policy_threat.json"
IRC_BIN = "/app/environment/irc/cmd/irc"


def _run(args, check=True):
    return subprocess.run(
        [IRC_BIN, *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _reset(policy_path=None):
    if STATE.exists():
        shutil.rmtree(STATE)
    shutil.copytree(FIX, STATE)
    if policy_path is not None:
        shutil.copy2(policy_path, STATE / "eval_policy.json")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(FIX / "staging", OUT)
    for child in OUT.iterdir():
        if child.is_file():
            child.unlink()


def _stage_intent(payload: dict):
    staging = STATE / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(FIX / "staging", staging)
    (staging / "intent.json").write_text(json.dumps(payload))
    return staging


def _read_json(path):
    return json.loads(Path(path).read_text())


def _journal():
    text = (STATE / "journal.ndjson").read_text().strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _router_digest(router):
    blob = json.dumps(
        {
            "generation": router["generation"],
            "checkpoint_id": router["checkpoint_id"],
            "routes": router["routes"],
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _lineage_proof(tip, feature_epoch, router_digest, mat):
    fresh = "true" if mat["fresh"] else "false"
    payload = (
        f"{tip['seq']}|{tip['ckpt']}|{tip['generation']}|{feature_epoch}|"
        f"{router_digest}|{mat['epoch']}|{fresh}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _assert_eval_consistent():
    bind = _read_json(EVAL)
    router = _read_json(STATE / "router.json")
    mat = _read_json(STATE / "materialized.json")
    tip = [e for e in _journal() if e["complete"]][-1]
    digest = _router_digest(router)
    assert bind["router_digest"] == digest
    assert bind["checkpoint_id"] == tip["ckpt"]
    assert bind["generation"] == tip["generation"]
    assert bind["journal_tip_seq"] == tip["seq"]
    assert bind["lineage_proof"] == _lineage_proof(
        tip, bind["feature_epoch"], digest, mat
    )
    return bind


def test_q01_baseline_status_and_materialization():
    """Baseline fixtures: tip ckpt_root with fresh materialization."""
    _reset()
    assert _run(["status"]).returncode == 0
    st = _read_json(STATUS)
    assert st["generation"] == 1
    assert st["active_checkpoint"] == "ckpt_root"
    assert st["materialization_fresh"] is True
    mat = _read_json(STATE / "materialized.json")
    assert mat["epoch"] == 2 and mat["fresh"] is True


def test_q02_promote_couples_feature_router_materialization():
    """Promote mid advances generation and refreshes feature + materialization + router."""
    _reset()
    assert _run(["promote", "--ckpt", "ckpt_mid"]).returncode == 0
    assert not (STATE / "staging").exists()
    feature_bind = _read_json(STATE / "feature_bind.json")
    materialized = _read_json(STATE / "materialized.json")
    router = _read_json(STATE / "router.json")
    assert feature_bind["feature_epoch"] == 3 and feature_bind["valid"] is True
    assert (
        materialized["epoch"] == 3
        and materialized["generation"] == 2
        and materialized["fresh"] is True
    )
    assert router["checkpoint_id"] == "ckpt_mid" and router["generation"] == 2
    _run(["eval-bind"])
    bind = _assert_eval_consistent()
    assert bind["compatible"] is True
    assert bind["feature_epoch"] == 3


def test_q03_compat_and_state_freeze_on_bad_tokenizer():
    """Bad tokenizer fails without mutating tip, router, feature, or materialization."""
    _reset()
    before = {
        "journal": (STATE / "journal.ndjson").read_bytes(),
        "router": (STATE / "router.json").read_text(),
        "feature_bind": (STATE / "feature_bind.json").read_text(),
        "materialized": (STATE / "materialized.json").read_text(),
    }
    assert _run(["promote", "--ckpt", "ckpt_badtok"], check=False).returncode == 2
    assert (STATE / "journal.ndjson").read_bytes() == before["journal"]
    assert (STATE / "router.json").read_text() == before["router"]
    assert (STATE / "feature_bind.json").read_text() == before["feature_bind"]
    assert (STATE / "materialized.json").read_text() == before["materialized"]


def test_q04_lineage_gate_blocks_tip_without_ancestor():
    """Promote tip before mid ever tipped must fail lineage gate."""
    _reset()
    before = (STATE / "journal.ndjson").read_bytes()
    assert _run(["promote", "--ckpt", "ckpt_tip"], check=False).returncode == 2
    assert (STATE / "journal.ndjson").read_bytes() == before
    _run(["status"])
    assert _read_json(STATUS)["active_checkpoint"] == "ckpt_root"


def test_q05_idempotent_promote_preserves_seq():
    """Re-promoting active tip does not append journal events."""
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    j1 = _journal()
    assert _run(["promote", "--ckpt", "ckpt_mid"]).returncode == 0
    j2 = _journal()
    assert len(j2) == len(j1)
    tip_after = j2[len(j2) - 1]
    assert tip_after["generation"] == 2


def test_q06_rollback_rebinding_cascade():
    """Rollback restores feature, materialization, and router together."""
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    _run(["promote", "--ckpt", "ckpt_tip"])
    assert _run(["rollback", "--generation", "2"]).returncode == 0
    feature_bind = _read_json(STATE / "feature_bind.json")
    materialized = _read_json(STATE / "materialized.json")
    router = _read_json(STATE / "router.json")
    assert feature_bind["feature_epoch"] == 3
    assert (
        materialized["epoch"] == 3
        and materialized["generation"] == 2
        and materialized["fresh"] is True
    )
    assert router["checkpoint_id"] == "ckpt_mid" and router["generation"] == 2
    _run(["eval-bind"])
    bind = _assert_eval_consistent()
    assert bind["checkpoint_id"] == "ckpt_mid"
    assert bind["compatible"] is True


def test_q07_recover_authority_and_stale_materialization():
    """Recover drops incomplete events, clears staging, journal overrides registry.

    If materialization still matches tip after recover it stays fresh; mismatched
    materialization becomes stale and eval-bind must report compatible false when
    freshness is required.
    """
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    # Force materialization out of sync while journal tip is mid
    (STATE / "materialized.json").write_text(
        json.dumps({"epoch": 9, "generation": 9, "fresh": True}, indent=2) + "\n"
    )
    with (STATE / "journal.ndjson").open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "seq": 99,
                    "op": "promote",
                    "ckpt": "ckpt_tip",
                    "generation": 3,
                    "complete": False,
                    "feature_epoch": 4,
                }
            )
            + "\n"
        )
    staging = _stage_intent({"ckpt": "ckpt_tip"})
    reg = _read_json(STATE / "registry.json")
    reg["active"] = "ckpt_tip"
    (STATE / "registry.json").write_text(json.dumps(reg, indent=2) + "\n")

    assert _run(["recover"]).returncode == 0
    assert all(e["complete"] for e in _journal())
    assert not any(e.get("seq") == 99 for e in _journal())
    assert not staging.exists()
    _run(["status"])
    st = _read_json(STATUS)
    assert st["active_checkpoint"] == "ckpt_mid"
    assert st["generation"] == 2
    assert st["materialization_fresh"] is False
    _run(["eval-bind"])
    bind = _assert_eval_consistent()
    assert bind["checkpoint_id"] == "ckpt_mid"
    assert bind["compatible"] is False


def test_q08_heldout_threat_policy_rejects_under_epoch():
    """Held-out eval policy with min_feature_epoch=4 rejects mid-only tip."""
    _reset(policy_path=THREAT_POLICY)
    _run(["promote", "--ckpt", "ckpt_mid"])
    _run(["eval-bind"])
    bind = _assert_eval_consistent()
    assert bind["feature_epoch"] == 3
    assert bind["compatible"] is False
    _run(["promote", "--ckpt", "ckpt_tip"])
    _run(["eval-bind"])
    bind2 = _assert_eval_consistent()
    assert bind2["feature_epoch"] == 4
    assert bind2["compatible"] is True


def test_q09_decisive_overlap_then_lineage_promote():
    """Incomplete tip staging + desynced registry + recover, then legal tip promote.

    Cascade: status/eval-bind after recover stay on mid; tip promote then couples
    generation 3, feature epoch 4, fresh materialization, and lineage_proof.
    """
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    _stage_intent({"ckpt": "ckpt_tip", "generation": 3, "seq": 50})
    with (STATE / "journal.ndjson").open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "seq": 50,
                    "op": "promote",
                    "ckpt": "ckpt_tip",
                    "generation": 3,
                    "complete": False,
                    "feature_epoch": 4,
                }
            )
            + "\n"
        )
    reg = _read_json(STATE / "registry.json")
    reg["active"] = "ckpt_tip"
    (STATE / "registry.json").write_text(json.dumps(reg, indent=2) + "\n")

    _run(["recover"])
    _run(["eval-bind"])
    bind = _assert_eval_consistent()
    assert bind["checkpoint_id"] == "ckpt_mid"
    assert bind["generation"] == 2

    assert _run(["promote", "--ckpt", "ckpt_tip"]).returncode == 0
    assert not (STATE / "staging").exists()
    _run(["eval-bind"])
    bind2 = _assert_eval_consistent()
    assert bind2["checkpoint_id"] == "ckpt_tip"
    assert bind2["generation"] == 3
    assert bind2["feature_epoch"] == 4
    assert bind2["compatible"] is True
    materialized = _read_json(STATE / "materialized.json")
    assert materialized["fresh"] is True and materialized["epoch"] == 4


def test_q10_adapter_compat_after_mid():
    """Bad adapter after mid promote must not advance tip or spoil materialization."""
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    materialized_before = (STATE / "materialized.json").read_text()
    assert _run(["promote", "--ckpt", "ckpt_badadp"], check=False).returncode == 2
    assert (STATE / "materialized.json").read_text() == materialized_before
    _run(["status"])
    assert _read_json(STATUS)["active_checkpoint"] == "ckpt_mid"


def test_q11_determinism_and_proof_stability():
    """Identical sequences yield identical eval_binding including lineage_proof."""
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    _run(["promote", "--ckpt", "ckpt_tip"])
    _run(["eval-bind"])
    first = EVAL.read_text()
    first_j = (STATE / "journal.ndjson").read_bytes()
    _reset()
    _run(["promote", "--ckpt", "ckpt_mid"])
    _run(["promote", "--ckpt", "ckpt_tip"])
    _run(["eval-bind"])
    assert EVAL.read_text() == first
    assert (STATE / "journal.ndjson").read_bytes() == first_j


def test_q12_rebind_after_stale_recover_via_promote():
    """After stale materialization recover, promote mid again refreshes and passes eval."""
    _reset(policy_path=THREAT_POLICY)
    _run(["promote", "--ckpt", "ckpt_mid"])
    (STATE / "materialized.json").write_text(
        json.dumps({"epoch": 1, "generation": 1, "fresh": True}, indent=2) + "\n"
    )
    _run(["recover"])
    _run(["eval-bind"])
    assert _assert_eval_consistent()["compatible"] is False
    # idempotent re-promote mid should refresh materialization
    assert _run(["promote", "--ckpt", "ckpt_mid"]).returncode == 0
    materialized = _read_json(STATE / "materialized.json")
    assert materialized["epoch"] == 3 and materialized["fresh"] is True
    _run(["promote", "--ckpt", "ckpt_tip"])
    _run(["eval-bind"])
    assert _assert_eval_consistent()["compatible"] is True
