import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path("/app/output/graph_probe.json")
NEST = Path("/app/environment/nest")
VAR = Path("/app/environment/var")
LEDGER = VAR / "ledger.jsonl"
SNAP = VAR / "snapshot.json"
SHADOW = VAR / "shadow.json"
STUB = Path("/app/environment/seed/stub_trace.json")
G1 = Path("/app/environment/seed/tile_g1.json")
G2 = Path("/app/environment/seed/tile_g2.json")
G1X = Path("/app/environment/seed/tile_g1_x2.json")
G2X = Path("/app/environment/seed/tile_g2_x2.json")
E1 = Path("/app/environment/seed/tile_e1.json")
E2 = Path("/app/environment/seed/tile_e2.json")
SCRAPS = "/app/environment/seed/scrap_old.txt,/app/environment/seed/scrap_new.txt"
TRIAD = (
    "/app/environment/seed/scrap_old.txt,"
    "/app/environment/seed/scrap_mid.txt,"
    "/app/environment/seed/scrap_new.txt"
)
REV_TRIAD = (
    "/app/environment/seed/scrap_mid.txt,"
    "/app/environment/seed/scrap_old.txt,"
    "/app/environment/seed/scrap_new.txt"
)
SUM = Path("/app/environment/seed/sum_partial.txt")
SUM_EQ = Path("/app/environment/seed/sum_equal.txt")

NEED_DUAL = {"root", "bind", "sys", "prop"}
NEED_A7 = {"root", "bind", "prop"}


def build() -> None:
    subprocess.run(
        ["bash", "/app/environment/tools/mk_all.sh"],
        cwd="/app",
        check=True,
        text=True,
        capture_output=True,
    )


def fresh() -> None:
    VAR.mkdir(parents=True, exist_ok=True)
    for p in (LEDGER, SNAP, SHADOW):
        if p.exists():
            p.unlink()
    if OUT.exists():
        OUT.unlink()
    (NEST / "go.mod").write_text("module example.com/nest\n\ngo 1.22\n")
    (NEST / "go.sum").write_text("")


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/app/bin/gm_infer", *args],
        cwd="/app",
        check=check,
        text=True,
        capture_output=True,
    )


def settle(
    g1: Path,
    g2: Path,
    *,
    arms: str = "a7,b2",
    scraps: str = SCRAPS,
    sum_path: Path = SUM,
    out: Path = OUT,
) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "settle",
            "--g1",
            str(g1),
            "--g2",
            str(g2),
            "--scraps",
            scraps,
            "--sum",
            str(sum_path),
            "--arms",
            arms,
            "--nest",
            str(NEST),
            "--var",
            str(VAR),
            "--out",
            str(out),
        ]
    )
    return json.loads(out.read_text())


def recover() -> dict:
    run_cmd(
        [
            "recover",
            "--nest",
            str(NEST),
            "--var",
            str(VAR),
            "--out",
            str(OUT),
        ]
    )
    return json.loads(OUT.read_text()) if OUT.exists() else {}


def status() -> dict:
    proc = run_cmd(["status", "--nest", str(NEST), "--var", str(VAR), "--out", str(OUT)])
    return json.loads(proc.stdout.strip())


def compact() -> None:
    run_cmd(["compact", "--var", str(VAR)])


def offline_build(pkg: str) -> None:
    subprocess.run(
        ["go", "build", "-o", f"/tmp/{pkg}.bin", f"./{pkg}"],
        cwd=str(NEST),
        check=True,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "GOPROXY": "off",
            "GOSUMDB": "off",
        },
    )


def view_digest(edges: list) -> str:
    payload = json.dumps({"edges": edges})
    proc = subprocess.run(
        ["python3", "/app/environment/tools/view_sum.py"],
        input=payload,
        cwd="/app",
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def auth_sums(g1: Path, g2: Path, sum_path: Path = SUM) -> dict[tuple[str, str], str]:
    t1 = json.loads(g1.read_text())
    t2 = json.loads(g2.read_text())
    pins: dict[tuple[str, str], str] = {}
    for line in sum_path.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3:
            pins[(fields[0], fields[1])] = fields[2]

    by_key: dict[tuple[str, str], list[tuple[int, str, int]]] = {}
    for idx, tile in enumerate((t1, t2)):
        gen = int(tile.get("gen", 0))
        for e in tile["entries"]:
            k = (e["module_path"], e["version"])
            by_key.setdefault(k, []).append((gen, e["sum"], idx))

    out: dict[tuple[str, str], str] = {}
    for k, opts in by_key.items():
        sums_present = {s for _, s, _ in opts}
        pin = pins.get(k)
        if pin and pin in sums_present:
            out[k] = pin
            continue
        if len(opts) == 1:
            out[k] = opts[0][1]
            continue
        opts_sorted = sorted(opts, key=lambda p: (p[0], p[2]))
        out[k] = opts_sorted[0][1]
    return out


def assert_probe(doc: dict, need: set[str], g1: Path, g2: Path, sum_path: Path = SUM) -> None:
    assert isinstance(doc["edges"], list)
    assert doc["edge_count"] == len(doc["edges"])
    assert doc["edges"], "settled report must include edges"
    assert view_digest(doc["edges"]) == doc["view_digest"]
    assert len(doc["view_digest"]) == 64
    assert doc["view_digest"] != "0" * 64
    classes = {e["cls"] for e in doc["edges"]}
    assert need <= classes
    sums = auth_sums(g1, g2, sum_path)
    for e in doc["edges"]:
        assert e["module_path"]
        assert e["version"]
        assert "replace_to" in e
        assert e["cls"]
        assert e["sum"] == sums[(e["module_path"], e["version"])]


def nest_text() -> str:
    return (NEST / "go.mod").read_text()


def gosum_text() -> str:
    return (NEST / "go.sum").read_text()


def ledger_lines() -> list[str]:
    if not LEDGER.exists():
        return []
    return [ln for ln in LEDGER.read_text().splitlines() if ln.strip()]


def committed_epochs() -> list[int]:
    out = []
    for ln in ledger_lines():
        row = json.loads(ln)
        if row.get("kind") == "commit" and not row.get("soft"):
            out.append(int(row["epoch"]))
    return out


def tip_epoch() -> int:
    epochs = committed_epochs()
    return epochs[-1] if epochs else 0


class TestQuarantineLedger:
    def test_dual_offline_settled_coherent(self) -> None:
        """Dual settle builds both packages offline with settled coherence."""
        build()
        fresh()
        doc = settle(G1, G2)
        assert_probe(doc, NEED_DUAL, G1, G2)
        offline_build("a7")
        offline_build("b2")
        assert status()["state"] == "settled"
        assert tip_epoch() >= 1
        assert "example.com/lib/legacy/v2" in nest_text()
        assert not SHADOW.exists()

    def test_soft_quarantine_blocks_until_recover(self) -> None:
        """Soft after hard leaves quarantine; recover restores settled tip."""
        build()
        fresh()
        first = settle(G1, G2)
        digest = first["view_digest"]
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        assert SHADOW.exists() or status()["state"] == "pending"
        assert status()["state"] == "pending"
        recovered = recover()
        assert recovered["view_digest"] == digest
        assert status()["state"] == "settled"
        assert not SHADOW.exists()
        assert_probe(recovered, NEED_DUAL, G1, G2)
        offline_build("a7")
        offline_build("b2")

    def test_cache_hit_clears_quarantine_restores_nest(self) -> None:
        """Identical settle after soft restores nest, clears shadow, keeps epoch."""
        build()
        fresh()
        first = settle(G1, G2)
        e1 = tip_epoch()
        n1 = len(ledger_lines())
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        (NEST / "go.mod").write_text(nest_text() + "\nrequire example.com/lib/extra v9.9.9\n")
        second = settle(G1, G2)
        assert second["view_digest"] == first["view_digest"]
        assert tip_epoch() == e1
        assert "example.com/lib/extra" not in nest_text()
        assert not SHADOW.exists()
        assert status()["state"] == "settled"
        assert_probe(second, NEED_DUAL, G1, G2)
        offline_build("a7")
        offline_build("b2")
        # soft row stripped on cache-hit; no new committed epoch row
        assert tip_epoch() == e1
        assert len(ledger_lines()) <= n1 + 1

    def test_arm_cut_restore_trims_and_advances(self) -> None:
        """Dual → a7 → dual trims nest, omits sys, advances epochs on arm change."""
        build()
        fresh()
        settle(G1, G2, arms="a7,b2")
        e0 = tip_epoch()
        assert "example.com/lib/b2x" in nest_text()
        cut = settle(G1, G2, arms="a7")
        assert tip_epoch() > e0
        classes = {e["cls"] for e in cut["edges"]}
        assert "sys" not in classes
        assert NEED_A7 <= classes
        assert "example.com/lib/b2x" not in nest_text()
        assert "example.com/lib/a7x" in nest_text()
        e1 = tip_epoch()
        restored = settle(G1, G2, arms="a7,b2")
        assert tip_epoch() > e1
        assert_probe(restored, NEED_DUAL, G1, G2)
        offline_build("b2")

    def test_scrap_flow_order_forces_new_epoch(self) -> None:
        """Triad then reverse triad flips replace polarity and advances epoch."""
        build()
        fresh()
        cleared = settle(G1, G2, scraps=TRIAD)
        e1 = tip_epoch()
        assert not any(e.get("replace_to") for e in cleared["edges"])
        assert "prop" not in {e["cls"] for e in cleared["edges"]}
        kept = settle(G1, G2, scraps=REV_TRIAD)
        assert tip_epoch() > e1
        assert any(e.get("replace_to") for e in kept["edges"])
        assert "prop" in {e["cls"] for e in kept["edges"]}

    def test_whitespace_scraps_keep_identity(self) -> None:
        """Whitespace/comment-only scrap edits do not append a new commit."""
        build()
        fresh()
        settle(G1, G2)
        e1 = tip_epoch()
        n1 = len(ledger_lines())
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "scrap_ws.txt"
            raw = Path("/app/environment/seed/scrap_old.txt").read_text()
            p.write_text("\n\n" + raw.replace("\t", "  ") + "\n// pad\n")
            scraps = f"{p},/app/environment/seed/scrap_new.txt"
            settle(G1, G2, scraps=scraps)
        assert tip_epoch() == e1
        assert len(ledger_lines()) == n1

    def test_pin_provenance_equal_gen_bind(self) -> None:
        """Pins need observed provenance; equal-gen bind uses applicable pin."""
        build()
        fresh()
        doc = settle(E1, E2, sum_path=SUM_EQ)
        assert_probe(doc, NEED_DUAL, E1, E2, sum_path=SUM_EQ)
        bind = [e for e in doc["edges"] if e["module_path"] == "example.com/lib/bind"]
        assert bind
        expected = None
        for line in SUM_EQ.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[0] == "example.com/lib/bind":
                expected = fields[2]
                break
        assert expected and bind[0]["sum"] == expected
        root = settle(G1, G2)
        sums = auth_sums(G1, G2)
        for e in root["edges"]:
            if e["module_path"] == "example.com/lib/root":
                assert e["sum"] == sums[("example.com/lib/root", "v1.0.0")]
        offline_build("a7")
        offline_build("b2")

    def test_replace_checksum_and_gosum_alignment(self) -> None:
        """Replace keeps original-module checksum; go.sum carries that sum line."""
        build()
        fresh()
        doc = settle(G1, G2)
        sums = auth_sums(G1, G2)
        legacy = [e for e in doc["edges"] if e["module_path"] == "example.com/lib/legacy"]
        assert legacy and legacy[0].get("replace_to")
        assert legacy[0]["cls"] == "prop"
        assert legacy[0]["sum"] == sums[("example.com/lib/legacy", "v1.0.0")]
        v2_sum = sums[("example.com/lib/legacy/v2", "v2.0.0")]
        assert legacy[0]["sum"] != v2_sum
        assert "example.com/lib/legacy/v2" in nest_text()
        assert sums[("example.com/lib/legacy", "v1.0.0")] in gosum_text()

    def test_torn_ledger_after_soft_recovers_tip(self) -> None:
        """Torn ledger after soft truncates; tip digest and settled status return."""
        build()
        fresh()
        first = settle(G1, G2)
        e1 = tip_epoch()
        digest = first["view_digest"]
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        with LEDGER.open("a") as fh:
            fh.write("{not-json\n")
            fh.write(
                json.dumps(
                    {
                        "seq": 99,
                        "parent_seal": "deadbeef",
                        "finger": "x" * 64,
                        "plan": {"edges": []},
                        "soft": False,
                        "epoch": e1 + 50,
                        "nest_seal": "y" * 64,
                        "plan_digest": "z" * 64,
                        "kind": "commit",
                    }
                )
                + "\n"
            )
        recovered = recover()
        assert recovered["view_digest"] == digest
        assert tip_epoch() == e1
        assert status()["state"] == "settled"
        assert not SHADOW.exists()
        assert_probe(recovered, NEED_DUAL, G1, G2)
        offline_build("a7")

    def test_snapshot_and_nest_staleness_pending(self) -> None:
        """Corrupt snapshot or nest alone flips pending until recover/cache-hit."""
        build()
        fresh()
        first = settle(G1, G2)
        assert status()["state"] == "settled"
        snap = json.loads(SNAP.read_text())
        snap["seal"] = "0" * 64
        SNAP.write_text(json.dumps(snap))
        assert status()["state"] == "pending"
        recover()
        assert status()["state"] == "settled"
        text = nest_text()
        (NEST / "go.mod").write_text(text + "\n// stale\n")
        assert status()["state"] == "pending"
        again = settle(G1, G2)
        assert again["view_digest"] == first["view_digest"]
        assert status()["state"] == "settled"
        OUT.write_text(json.dumps({"edges": [], "edge_count": 0, "view_digest": "0" * 64}))
        assert status()["state"] == "pending"

    def test_compact_preserves_epochs_after_quarantine(self) -> None:
        """Compact after multi-epoch+soft keeps tip digest/epoch; settle stays no-op."""
        build()
        fresh()
        settle(G1, G2, arms="a7")
        dual = settle(G1, G2, arms="a7,b2")
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        e_before = tip_epoch()
        digest = dual["view_digest"]
        compact()
        assert not SHADOW.exists()
        recovered = recover()
        assert recovered["view_digest"] == digest
        assert tip_epoch() == e_before
        n = len(ledger_lines())
        again = settle(G1, G2, arms="a7,b2")
        assert again["view_digest"] == digest
        assert tip_epoch() == e_before
        assert len(ledger_lines()) == n
        offline_build("a7")
        offline_build("b2")

    def test_probe_shadow_status_matrix(self) -> None:
        """Probe-only staleness and shadow presence both report pending."""
        build()
        fresh()
        settle(G1, G2)
        assert status()["state"] == "settled"
        shutil.copy(STUB, OUT)
        assert status()["state"] == "pending"
        recover()
        assert status()["state"] == "settled"
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        assert status()["state"] == "pending"
        assert SHADOW.exists()

    def test_cross_command_arm_change_after_soft(self) -> None:
        """Soft quarantine, then different arms hard settle, compact, recover."""
        build()
        fresh()
        settle(G1, G2, arms="a7,b2")
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        assert status()["state"] == "pending"
        cut = settle(G1, G2, arms="a7")
        assert status()["state"] == "settled"
        assert "sys" not in {e["cls"] for e in cut["edges"]}
        compact()
        recovered = recover()
        assert recovered["view_digest"] == cut["view_digest"]
        assert status()["state"] == "settled"
        offline_build("a7")

    def test_long_quarantine_tear_heldout_lineage(self) -> None:
        """Arm cut, soft, torn ledger, recover, compact, held-out settle lineage."""
        build()
        fresh()
        settle(G1, G2, arms="a7")
        e_a = tip_epoch()
        settle(G1, G2, arms="a7,b2")
        e_b = tip_epoch()
        assert e_b > e_a
        settle(G2, G2, scraps="/app/environment/seed/scrap_new.txt")
        with LEDGER.open("a") as fh:
            fh.write("CORRUPT\n")
        recover()
        compact()
        held = settle(G1X, G2X)
        e_c = tip_epoch()
        assert e_c > e_b
        assert_probe(held, NEED_DUAL, G1X, G2X)
        assert any(e.get("replace_to") for e in held["edges"])
        assert status()["state"] == "settled"
        assert not SHADOW.exists()
        epochs = committed_epochs()
        assert epochs == sorted(epochs)
        offline_build("a7")
        offline_build("b2")

    def test_idempotent_after_materialization_corruption(self) -> None:
        """Corrupt nest+probe between runs; identical settle rematerializes no-op."""
        build()
        fresh()
        first = settle(G1, G2)
        e1 = tip_epoch()
        (NEST / "go.mod").write_text("module example.com/nest\ngo 1.22\n")
        (NEST / "go.sum").write_text("")
        shutil.copy(STUB, OUT)
        assert status()["state"] == "pending"
        second = settle(G1, G2)
        assert second["view_digest"] == first["view_digest"]
        assert tip_epoch() == e1
        assert_probe(second, NEED_DUAL, G1, G2)
        assert status()["state"] == "settled"
        offline_build("a7")
        offline_build("b2")
