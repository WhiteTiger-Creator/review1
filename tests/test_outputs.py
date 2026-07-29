"""Verifier for averaged-perceptron train ledger coherence."""


import json
import shutil
import subprocess
from pathlib import Path

BIN = Path("/app/bin/percctl")
LEDGER = Path("/app/output/perc_ledger.json")
MODEL = Path("/app/var/model")
ACTIVE = MODEL / "active.page"
STANDBY = MODEL / "standby.page"
PARTIAL = MODEL / "active.page.partial"
SUITE = "/app/environment/fixtures/suite.json"
RESUME = "/app/environment/fixtures/resume.json"
PRISTINE = Path("/opt/verifier-fixtures/environment")
ENV = Path("/app/environment")
BOOT_PERSIST = 0xA11E
OUT = Path("/app/output")


def _fnv32(data: str) -> str:
    h = 2166136261
    for b in data.encode():
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, cwd="/app", text=True, capture_output=True)


def _rebuild() -> None:
    subprocess.run(["/app/environment/ci/build.sh"], check=True, cwd="/app")


def _reset_model() -> None:
    if MODEL.exists():
        shutil.rmtree(MODEL)
    MODEL.mkdir(parents=True)
    if LEDGER.exists():
        LEDGER.unlink()


def _cycle(suite: str = SUITE) -> dict:
    _run([str(BIN), "cycle", suite], check=True)
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _resume_probe() -> dict:
    _run([str(BIN), "resume-probe"], check=True)
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _rows(data: dict, action: str | None = None, case_id: str | None = None) -> list[dict]:
    out = []
    for r in data.get("runs", []):
        if action is not None and r.get("action") != action:
            continue
        if case_id is not None and r.get("case_id") != case_id:
            continue
        out.append(r)
    return out


def _fresh_cycle() -> dict:
    _rebuild()
    _reset_model()
    return _cycle()


def _ref_after_suite() -> tuple[int, int, str, str, str, str]:
    """Independent reference: updates, pred(e_solo), dig/fence gen1, dig/fence gen2."""
    order = ["color", "shape", "bulk", "texture"]
    active = {"color": 0, "shape": 0, "bulk": 1, "texture": 1}
    w = {k: 0.0 for k in order}
    u = {k: 0.0 for k in order}
    bias = 0.0
    ubias = 0.0
    updates = 0

    def margin(label: int, feats: list[str]) -> float:
        s = bias + sum(w[f] for f in feats if active[f])
        return label * s

    def train(label: int, feats: list[str]) -> int:
        nonlocal bias, ubias, updates
        if margin(label, feats) > 0:
            return 0
        updates += 1
        for f in feats:
            if not active[f]:
                continue
            w[f] += label
            u[f] += w[f]
        bias += label
        ubias += bias
        return 1

    train(1, ["bulk", "texture"])
    train(-1, ["bulk"])
    assert train(1, ["bulk", "texture"]) == 0
    train(-1, ["bulk"])

    def avg(f: str) -> float:
        return u[f] / updates if updates else w[f]

    def avg_b() -> float:
        return ubias / updates if updates else bias

    def digest(gen: int) -> str:
        parts = [f"g={gen}|u={updates}|"]
        for name in order:
            if active[name]:
                parts.append(f"{name}:{avg(name):.6f},")
        parts.append(f"b={avg_b():.6f}")
        return _fnv32("".join(parts))

    def fence(gen: int) -> str:
        dig = digest(gen)
        return _fnv32(f"{dig}|{gen}|{updates}")

    s = avg_b() + avg("bulk")
    pred = 1 if s >= 0 else -1
    return updates, pred, digest(1), fence(1), digest(2), fence(2)


def _micro_digest(active: dict[str, int], updates: int, avgs: dict[str, float], bias: float, gen: int = 1) -> str:
    order = ["color", "shape", "bulk", "texture"]
    parts = [f"g={gen}|u={updates}|"]
    for name in order:
        if active.get(name):
            parts.append(f"{name}:{avgs.get(name, 0.0):.6f},")
    parts.append(f"b={bias:.6f}")
    return _fnv32("".join(parts))


def test_schema_and_persist_boot() -> None:
    """Ledger schema, journal path, generation, updates, and persist id settle."""
    data = _fresh_cycle()
    assert data["schema"] == "perc_model_v1"
    assert data["journal_path"] == "/app/var/model/active.page"
    assert isinstance(data["journal_generation"], int)
    assert data["journal_generation"] >= 2
    assert isinstance(data["deny_count"], int)
    assert isinstance(data["updates"], int)
    assert data["updates"] == 3
    assert isinstance(data["runs"], list)
    for r in data["runs"]:
        assert r["persist_id"] == BOOT_PERSIST


def test_declaration_order_not_alpha() -> None:
    """Declaration merge leaves color/shape inactive; alpha merge activates them."""
    data = _fresh_cycle()
    _upd, _pred, dig_g1, fen_g1, _d2, _f2 = _ref_after_suite()
    preds = _rows(data, action="predict", case_id="e_solo")
    assert preds
    assert preds[0]["digest"] == dig_g1
    assert preds[0]["fence"] == fen_g1

    man = ENV / "fixtures" / "manifest.json"
    backup = man.read_text(encoding="utf-8")
    try:
        man.write_text(
            json.dumps(
                {
                    "packs": [
                        "fixtures/packs/aa_edge.feats",
                        "fixtures/packs/mm_mid.feats",
                        "fixtures/packs/zz_site.feats",
                    ]
                }
            ),
            encoding="utf-8",
        )
        _reset_model()
        OUT.mkdir(parents=True, exist_ok=True)
        micro = OUT / "fold_only.json"
        micro.write_text(
            json.dumps(
                {
                    "cases": "fixtures/cases/examples.json",
                    "actions": [
                        {"op": "fold"},
                        {"op": "train", "case": "e_pos"},
                        {"op": "predict", "case": "e_hold"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        alt = _cycle(str(micro))
    finally:
        man.write_text(backup, encoding="utf-8")
    alt_preds = _rows(alt, action="predict", case_id="e_hold")
    assert alt_preds
    decl_micro = _micro_digest(
        {"color": 0, "shape": 0, "bulk": 1, "texture": 1},
        1,
        {"bulk": 1.0, "texture": 1.0},
        1.0,
    )
    assert alt_preds[0]["digest"] != decl_micro
    assert alt_preds[0]["digest"] != dig_g1


def test_margin_skip_gates_update() -> None:
    """Positive-margin examples must skip without advancing the update counter."""
    data = _fresh_cycle()
    skips = _rows(data, action="train", case_id="e_skip")
    assert skips and skips[0]["outcome"] == "skip"
    assert skips[0]["reason"] == "MARGIN_OK"
    assert data["updates"] == 3


def test_averaged_predict_not_last_plane() -> None:
    """e_solo is +1 on averaged plane and -1 on last plane after the suite."""
    data = _fresh_cycle()
    _upd, pred_ref, dig_g1, fen_g1, _d2, _f2 = _ref_after_suite()
    assert pred_ref == 1
    preds = _rows(data, action="predict", case_id="e_solo")
    assert len(preds) >= 2
    assert preds[0]["pred"] == 1
    assert preds[0]["outcome"] == "ok"
    assert preds[0]["digest"] == dig_g1
    assert preds[0]["fence"] == fen_g1


def test_cut_delayed_reseal_digest() -> None:
    """After cut, prediction still uses averaged plane but digest binds new generation."""
    data = _fresh_cycle()
    _upd, _pred, dig_g1, _f1, dig_g2, fen_g2 = _ref_after_suite()
    preds = _rows(data, action="predict", case_id="e_solo")
    assert len(preds) >= 2
    post = preds[1]
    assert post["epoch"] >= 2
    assert post["pred"] == 1
    assert post["digest"] == dig_g2
    assert post["fence"] == fen_g2
    assert post["digest"] != dig_g1


def test_torn_active_recovers_standby() -> None:
    """Recover after tear must rematerialize standby generation onto active."""
    data = _fresh_cycle()
    rec = _rows(data, action="recover")
    assert rec, "expected recover action"
    assert rec[0]["epoch"] >= 2
    assert rec[0]["lineage_skew"] == 0
    assert rec[0]["notes"] == "had_partial"
    assert ACTIVE.exists()
    text = ACTIVE.read_text(encoding="utf-8")
    assert int(text.splitlines()[0].split()[1]) >= 2


def test_resume_rehydrates_fence() -> None:
    """Resume probe must rehydrate durable pages with coherent digest/fence."""
    _rebuild()
    _reset_model()
    _cycle(RESUME)
    data = _resume_probe()
    _upd, _pred, _d1, _f1, dig_g2, fen_g2 = _ref_after_suite()
    assert data["schema"] == "perc_model_v1"
    for r in data["runs"]:
        assert r["persist_id"] == BOOT_PERSIST
    preds = _rows(data, action="predict", case_id="e_solo")
    assert preds and preds[0]["outcome"] == "ok"
    assert preds[0]["pred"] == 1
    assert preds[0]["digest"] == dig_g2
    assert preds[0]["fence"] == fen_g2


def test_idempotent_cycle_digest() -> None:
    """Two fresh rebuild cycles must emit identical post-cut digests."""
    a = _fresh_cycle()
    b = _fresh_cycle()
    pa = _rows(a, action="predict", case_id="e_solo")[-1]
    pb = _rows(b, action="predict", case_id="e_solo")[-1]
    assert pa["digest"] == pb["digest"]
    assert pa["fence"] == pb["fence"]
    assert a["updates"] == b["updates"] == 3


def test_cross_artifact_page_matches_ledger() -> None:
    """Active page generation/updates must match the ledger journal fields."""
    data = _fresh_cycle()
    assert data["journal_generation"] >= 2
    page = ACTIVE.read_text(encoding="utf-8")
    gen = int(page.splitlines()[0].split()[1])
    upd = int(page.splitlines()[1].split()[1])
    assert gen == data["journal_generation"]
    assert upd == data["updates"]
    assert STANDBY.exists()
    if PARTIAL.exists():
        raise AssertionError("partial marker must be cleared after recover")


def test_negative_torn_without_recover_is_skewed() -> None:
    """Negative: stop after tear; active page stays torn generation 0."""
    _rebuild()
    _reset_model()
    OUT.mkdir(parents=True, exist_ok=True)
    micro = OUT / "tear_only.json"
    micro.write_text(
        json.dumps(
            {
                "cases": "fixtures/cases/examples.json",
                "actions": [
                    {"op": "fold"},
                    {"op": "train", "case": "e_pos"},
                    {"op": "cut"},
                    {"op": "publish"},
                    {"op": "tear"},
                ],
            }
        ),
        encoding="utf-8",
    )
    _cycle(str(micro))
    assert PARTIAL.exists()
    gen = int(ACTIVE.read_text(encoding="utf-8").splitlines()[0].split()[1])
    assert gen == 0
    st_gen = int(STANDBY.read_text(encoding="utf-8").splitlines()[0].split()[1])
    assert st_gen >= 2


def test_static_json_insufficient() -> None:
    """Stubbing drv/emit.c must not leave a hand-written ledger as a pass."""
    _rebuild()
    _reset_model()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(
        json.dumps(
            {
                "schema": "perc_model_v1",
                "journal_path": "/app/var/model/active.page",
                "journal_generation": 7,
                "deny_count": 0,
                "updates": 3,
                "runs": [],
            }
        ),
        encoding="utf-8",
    )
    emit = ENV / "drv" / "emit.c"
    backup = emit.read_text(encoding="utf-8")
    try:
        emit.write_text(
            '#include "ops.h"\nint emit_ledger(const struct desk *d){ (void)d; return 0; }\n',
            encoding="utf-8",
        )
        _rebuild()
        _reset_model()
        _run([str(BIN), "cycle", SUITE], check=False)
        assert (not LEDGER.exists()) or json.loads(LEDGER.read_text()).get("journal_generation") != 7
    finally:
        emit.write_text(backup, encoding="utf-8")
        _rebuild()


def test_source_diverges_from_pristine() -> None:
    """Solver-visible sources under opaque packages must diverge from pristine."""
    _rebuild()
    assert PRISTINE.exists()
    diverged = False
    for rel in ("v3/fold.c", "w6/score.c", "x1/step.c", "y8/page.c"):
        a = (ENV / rel).read_text(encoding="utf-8")
        b = (PRISTINE / rel).read_text(encoding="utf-8")
        if a != b:
            diverged = True
            break
    assert diverged, "expected source edits under opaque training modules"
