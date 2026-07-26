#!/usr/bin/env python3
"""Verifier: chironym selective-risk evaluation artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ENV = Path("/app/environment")
OUT = Path("/app/output")
VAR = Path("/app/var")
BIN = Path("/tmp/chironym_vbin")
CTL = BIN / "chironymctl"
EMBED = BIN / "k7"
ALIGN = BIN / "m3"
STUDIO_A = ENV / "data/campaigns/studio_a"
STUDIO_B = ENV / "fixtures/studio_b"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fnv1a32(s: str) -> int:
    h = 2166136261
    for ch in s.encode():
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def l2_normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        return v
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def match_rate(hyp: list[str], ref: list[str]) -> float:
    n, m = len(hyp), len(ref)
    lim = min(n, m)
    eq = sum(1 for i in range(lim) if hyp[i] == ref[i])
    return (eq / lim) * (lim / max(n, m))


def softmin(gamma: float, x: float, y: float, z: float) -> float:
    return -gamma * math.log(math.exp(-x / gamma) + math.exp(-y / gamma) + math.exp(-z / gamma))


def fit_embeddings(pack: dict, pol: dict) -> dict[str, list[float]]:
    vocab = sorted(
        {
            t
            for u in pack["utterances"]
            for t in list(u["hyp"]) + list(u["ref"])
        }
    )
    dim = pol["embed_dim"]
    emb: dict[str, list[float]] = {}
    for t in vocab:
        h = (fnv1a32(t) % 10007) + 1
        v = [math.sin(h * (k + 1) * 1e-3) for k in range(dim)]
        emb[t] = l2_normalize(v)
    pairs = []
    for u in pack["utterances"]:
        if u["fold"] != "train":
            continue
        for i in range(min(len(u["hyp"]), len(u["ref"]))):
            pairs.append((u["hyp"][i], u["ref"][i]))
    lr = pol["infonce_lr"]
    for _ in range(pol["infonce_steps"]):
        for a_tok, p_tok in pairs:
            a = emb[a_tok][:]
            p = emb[p_tok][:]
            mid = l2_normalize([a[k] + p[k] for k in range(dim)])
            na = l2_normalize([(1 - lr) * a[k] + lr * mid[k] for k in range(dim)])
            np = l2_normalize([(1 - lr) * p[k] + lr * mid[k] for k in range(dim)])
            emb[a_tok] = na
            emb[p_tok] = np
    return emb


def soft_dtw_score(hyp, ref, emb, gamma, gap) -> float:
    n, m = len(hyp), len(ref)
    c = [[1.0 - cosine(emb[hyp[i]], emb[ref[j]]) for j in range(m)] for i in range(n)]
    r = [[0.0] * m for _ in range(n)]
    r[0][0] = c[0][0]
    for i in range(1, n):
        r[i][0] = c[i][0] + r[i - 1][0] + gap
    for j in range(1, m):
        r[0][j] = c[0][j] + r[0][j - 1] + gap
    for i in range(1, n):
        for j in range(1, m):
            r[i][j] = c[i][j] + softmin(gamma, r[i - 1][j], r[i][j - 1], r[i - 1][j - 1])
    raw = r[n - 1][m - 1]
    return 1.0 / (1.0 + raw / max(n, m))


def embed_digest(emb: dict[str, list[float]]) -> str:
    parts = []
    for k in sorted(emb):
        parts.append(k)
        parts.append(",".join(f"{x:.6f}" for x in emb[k]))
    blob = "\n".join(parts) + "\n"
    return sha256_bytes(blob.encode())


def expected_bundle(camp_dir: Path) -> dict:
    pack_bytes = (camp_dir / "pack.json").read_bytes()
    pol_bytes = (camp_dir / "policy.json").read_bytes()
    pack = json.loads(pack_bytes)
    pol = json.loads(pol_bytes)
    emb = fit_embeddings(pack, pol)
    ed = embed_digest(emb)
    rows = []
    for u in pack["utterances"]:
        score = soft_dtw_score(u["hyp"], u["ref"], emb, pol["soft_dtw_gamma"], pol["gap_cost"])
        mr = match_rate(u["hyp"], u["ref"])
        y = 1 if mr >= 0.75 else 0
        rows.append({"utt": u, "score": score, "y": y})
    best_t = pol["temp_grid"][0]
    best_nll = float("inf")
    for T in pol["temp_grid"]:
        nll = 0.0
        n = 0
        for r in rows:
            if r["utt"]["fold"] != "calib":
                continue
            p = sigmoid(r["score"] / T)
            y = r["y"]
            nll += -(y * math.log(p + 1e-12) + (1 - y) * math.log(1 - p + 1e-12))
            n += 1
        nll /= max(n, 1)
        if nll < best_nll or (nll == best_nll and T < best_t):
            best_nll = nll
            best_t = T
    for r in rows:
        r["conf"] = sigmoid(r["score"] / best_t)
    calib = [r for r in rows if r["utt"]["fold"] == "calib"]
    best_thr = pol["thr_grid"][-1]
    best_cov = -1.0
    found = False
    for thr in pol["thr_grid"]:
        accepted = [r for r in calib if r["conf"] >= thr]
        if not accepted:
            continue
        cov = len(accepted) / len(calib)
        risk = sum(1 - r["y"] for r in accepted) / len(accepted)
        if risk <= pol["risk_target"]:
            if not found or cov > best_cov or (cov == best_cov and thr < best_thr):
                found = True
                best_cov = cov
                best_thr = thr
    for r in rows:
        r["accepted"] = r["conf"] >= best_thr

    def cov_risk(fold: str):
        xs = [r for r in rows if r["utt"]["fold"] == fold]
        if not xs:
            return 0.0, 0.0
        acc = [r for r in xs if r["accepted"]]
        cov = len(acc) / len(xs)
        risk = (sum(1 - r["y"] for r in acc) / len(acc)) if acc else 0.0
        return cov, risk

    calib_cov, calib_risk = cov_risk("calib")
    eval_cov, eval_risk = cov_risk("eval")
    pd, pold = sha256_bytes(pack_bytes), sha256_bytes(pol_bytes)
    bd = sha256_bytes(
        f"{pd}:{pold}:{ed}:{best_thr:.4f}:{best_t:.4f}".encode()
    )
    utt_sorted = sorted(rows, key=lambda r: r["utt"]["utt_id"])
    return {
        "campaign_id": pack["campaign_id"],
        "pack_digest": pd,
        "policy_digest": pold,
        "embed_digest": ed,
        "bundle_digest": bd,
        "temperature": best_t,
        "threshold": best_thr,
        "calib_coverage": calib_cov,
        "calib_risk": calib_risk,
        "eval_coverage": eval_cov,
        "eval_risk": eval_risk,
        "rows": utt_sorted,
    }


def rebuild():
    if BIN.exists():
        shutil.rmtree(BIN)
    BIN.mkdir(parents=True)
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(BIN / "target_k7")
    subprocess.check_call(
        ["cargo", "build", "--release", "--manifest-path", str(ENV / "k7/Cargo.toml")],
        cwd=str(ENV),
        env=env,
    )
    env["CARGO_TARGET_DIR"] = str(BIN / "target_m3")
    subprocess.check_call(
        ["cargo", "build", "--release", "--manifest-path", str(ENV / "m3/Cargo.toml")],
        cwd=str(ENV),
        env=env,
    )
    shutil.copy(BIN / "target_k7/release/k7", EMBED)
    shutil.copy(BIN / "target_m3/release/m3", ALIGN)
    EMBED.chmod(0o755)
    ALIGN.chmod(0o755)
    subprocess.check_call(["go", "build", "-o", str(CTL), "./cmd/chironymctl"], cwd=str(ENV))
    # also refresh /app/bin for process defaults
    shutil.copy(EMBED, "/app/bin/k7")
    shutil.copy(ALIGN, "/app/bin/m3")
    shutil.copy(CTL, "/app/bin/chironymctl")


def reset_io():
    if OUT.exists():
        shutil.rmtree(OUT)
    if VAR.exists():
        shutil.rmtree(VAR)
    OUT.mkdir(parents=True)
    VAR.mkdir(parents=True)
    memo = VAR / "chironym_align_memo.json"
    if memo.exists():
        memo.unlink()


def run_eval(campaign: Path, out: Path = OUT):
    env = os.environ.copy()
    env["CHIRONYM_EMBED_BIN"] = str(EMBED)
    env["CHIRONYM_ALIGN_BIN"] = str(ALIGN)
    subprocess.check_call([str(CTL), "prepare", "--output", str(out)], env=env)
    return subprocess.run(
        [str(CTL), "evaluate", "--campaign", str(campaign), "--output", str(out)],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _build_once():
    rebuild()


def assert_matches_expected(camp: Path, out: Path, stdout: str):
    exp = expected_bundle(camp)
    report = json.loads((out / "align_report.json").read_text())
    state = json.loads((out / "campaign_state.json").read_text())
    log = (out / "eval_summary.log").read_text().splitlines()
    csv_lines = (out / "utterance_scores.csv").read_text().splitlines()
    assert report["campaign_id"] == exp["campaign_id"]
    assert report["pack_digest"] == exp["pack_digest"]
    assert report["policy_digest"] == exp["policy_digest"]
    assert report["embed_digest"] == exp["embed_digest"]
    assert report["bundle_digest"] == exp["bundle_digest"]
    assert abs(report["temperature"] - exp["temperature"]) < 1e-9
    assert abs(report["threshold"] - exp["threshold"]) < 1e-9
    assert abs(report["eval_coverage"] - exp["eval_coverage"]) < 1e-6
    assert abs(report["eval_risk"] - exp["eval_risk"]) < 1e-6
    assert abs(report["calib_coverage"] - exp["calib_coverage"]) < 1e-6
    assert abs(report["calib_risk"] - exp["calib_risk"]) < 1e-6
    assert state["bundle_digest"] == exp["bundle_digest"]
    assert state["epoch"] >= 1
    assert f"BUNDLE_DIGEST={exp['bundle_digest']}" in stdout
    assert f"TOP_ACCEPT_RATE={exp['eval_coverage']:.6f}" in stdout
    assert f"EPOCH={state['epoch']}" in stdout
    assert log[0] == f"CAMPAIGN={exp['campaign_id']}"
    assert log[5] == f"BUNDLE_DIGEST={exp['bundle_digest']}"
    assert csv_lines[0] == "utt_id,fold,score,conf,accepted,y"
    by_id = {r["utt_id"]: r for r in report["utterances"]}
    for er in exp["rows"]:
        uid = er["utt"]["utt_id"]
        got = by_id[uid]
        assert abs(got["score"] - er["score"]) < 1e-5
        assert abs(got["conf"] - er["conf"]) < 1e-5
        assert got["accepted"] == er["accepted"]
        assert got["y"] == er["y"]
    # csv agreement
    for line in csv_lines[1:]:
        utt_id, fold, score, conf, accepted, y = line.split(",")
        got = by_id[utt_id]
        assert fold == got["fold"]
        assert abs(float(score) - got["score"]) < 1e-6
        assert abs(float(conf) - got["conf"]) < 1e-6
        assert int(accepted) == (1 if got["accepted"] else 0)
        assert int(y) == got["y"]
    ledger = json.loads((VAR / "chironym_ledger.json").read_text())
    assert ledger[-1]["bundle_digest"] == exp["bundle_digest"]
    hist = (out / "risk_history.jsonl").read_text().strip().splitlines()
    last = json.loads(hist[-1])
    assert last["bundle_digest"] == exp["bundle_digest"]
    mirror = json.loads((VAR / "chironym_state.json").read_text())
    assert mirror["bundle_digest"] == state["bundle_digest"]
    assert mirror["epoch"] == state["epoch"]


def test_studio_a_contract_bundle():
    reset_io()
    proc = run_eval(STUDIO_A)
    assert proc.returncode == 0, proc.stderr
    assert_matches_expected(STUDIO_A, OUT, proc.stdout)


def test_studio_b_fixture_bundle():
    reset_io()
    proc = run_eval(STUDIO_B)
    assert proc.returncode == 0, proc.stderr
    assert_matches_expected(STUDIO_B, OUT, proc.stdout)


def test_unarmed_fails_closed():
    reset_io()
    env = os.environ.copy()
    env["CHIRONYM_EMBED_BIN"] = str(EMBED)
    env["CHIRONYM_ALIGN_BIN"] = str(ALIGN)
    proc = subprocess.run(
        [str(CTL), "evaluate", "--campaign", str(STUDIO_A), "--output", str(OUT)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert proc.stderr.startswith("chironym output not armed:")
    assert not (VAR / "chironym_ledger.json").exists()


def test_invalid_campaign_fails_closed():
    reset_io()
    bad = OUT / "scratch_bad"
    bad.mkdir(parents=True)
    (bad / "pack.json").write_text("{}")
    # missing policy
    env = os.environ.copy()
    env["CHIRONYM_EMBED_BIN"] = str(EMBED)
    env["CHIRONYM_ALIGN_BIN"] = str(ALIGN)
    subprocess.check_call([str(CTL), "prepare", "--output", str(OUT)], env=env)
    proc = subprocess.run(
        [str(CTL), "evaluate", "--campaign", str(bad), "--output", str(OUT)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert proc.stderr.startswith("invalid chironym campaign:")
    assert not (VAR / "chironym_ledger.json").exists()


def test_repeat_stable_under_unchanged_inputs():
    reset_io()
    p1 = run_eval(STUDIO_A)
    assert p1.returncode == 0
    r1 = (OUT / "align_report.json").read_bytes()
    c1 = (OUT / "utterance_scores.csv").read_bytes()
    e1 = json.loads((OUT / "campaign_state.json").read_text())["epoch"]
    p2 = run_eval(STUDIO_A)
    assert p2.returncode == 0
    r2 = (OUT / "align_report.json").read_bytes()
    c2 = (OUT / "utterance_scores.csv").read_bytes()
    e2 = json.loads((OUT / "campaign_state.json").read_text())["epoch"]
    assert r1 == r2
    assert c1 == c2
    assert e2 == e1 + 1


def test_policy_gamma_mutation_refreshes_bundle():
    reset_io()
    scratch = OUT / "scratch_mut"
    shutil.copytree(STUDIO_A, scratch)
    p1 = run_eval(scratch)
    assert p1.returncode == 0
    d1 = json.loads((OUT / "align_report.json").read_text())["bundle_digest"]
    pol = json.loads((scratch / "policy.json").read_text())
    pol["soft_dtw_gamma"] = round(pol["soft_dtw_gamma"] + 0.17, 4)
    (scratch / "policy.json").write_text(json.dumps(pol, indent=2) + "\n")
    # new output dir to avoid history confusion; still same process memo
    out2 = OUT / "scratch_b"
    out2.mkdir()
    env = os.environ.copy()
    env["CHIRONYM_EMBED_BIN"] = str(EMBED)
    env["CHIRONYM_ALIGN_BIN"] = str(ALIGN)
    subprocess.check_call([str(CTL), "prepare", "--output", str(out2)], env=env)
    p2 = subprocess.run(
        [str(CTL), "evaluate", "--campaign", str(scratch), "--output", str(out2)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    d2 = json.loads((out2 / "align_report.json").read_text())["bundle_digest"]
    assert d1 != d2
    assert_matches_expected(scratch, out2, p2.stdout)


def test_pack_token_mutation_refreshes_scores():
    reset_io()
    scratch = OUT / "scratch_a"
    shutil.copytree(STUDIO_A, scratch)
    p1 = run_eval(scratch)
    assert p1.returncode == 0
    s1 = json.loads((OUT / "align_report.json").read_text())["utterances"][0]["score"]
    pack = json.loads((scratch / "pack.json").read_text())
    # mutate an eval hyp token
    for u in pack["utterances"]:
        if u["fold"] == "eval":
            u["hyp"][0] = u["hyp"][0] + "X"
            break
    (scratch / "pack.json").write_text(json.dumps(pack, indent=2) + "\n")
    out2 = OUT / "scratch_b"
    out2.mkdir()
    env = os.environ.copy()
    env["CHIRONYM_EMBED_BIN"] = str(EMBED)
    env["CHIRONYM_ALIGN_BIN"] = str(ALIGN)
    subprocess.check_call([str(CTL), "prepare", "--output", str(out2)], env=env)
    p2 = subprocess.run(
        [str(CTL), "evaluate", "--campaign", str(scratch), "--output", str(out2)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    assert_matches_expected(scratch, out2, p2.stdout)
    s2 = json.loads((out2 / "align_report.json").read_text())["utterances"][0]["score"]
    # not asserting s1!=s2 always, but digests must differ
    d1 = json.loads((OUT / "align_report.json").read_text())["bundle_digest"]
    d2 = json.loads((out2 / "align_report.json").read_text())["bundle_digest"]
    assert d1 != d2
    _ = s1, s2


def test_cross_artifact_cli_agreement():
    reset_io()
    proc = run_eval(STUDIO_A)
    assert proc.returncode == 0
    assert_matches_expected(STUDIO_A, OUT, proc.stdout)
