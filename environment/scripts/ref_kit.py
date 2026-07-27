"""Offline digest and cohort helpers aligned with /app/docs/cur_contract.md."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_pol(path: str | Path = "/app/docs/pol_a.toml") -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    out: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = [x.strip() for x in line.split("=", 1)]
        if val.startswith("["):
            inner = val.strip("[]")
            out[key] = [float(x.strip()) for x in inner.split(",") if x.strip()]
        elif "." in val:
            out[key] = float(val)
        else:
            try:
                out[key] = int(val)
            except ValueError:
                out[key] = val.strip('"')
    return out


def band_of(weight: float, cuts: list[float]) -> int:
    return sum(1 for c in cuts if weight > c)


def fmt_weight(w: float, decimals: int) -> str:
    return f"{w:.{decimals}f}"


def admit_hex(scenario_id: str, item_id: str, epoch: int, role: str, band: int) -> str:
    return sha16(f"{scenario_id}|{item_id}|{epoch}|{role}|{band}")


def fence_hex(admit: str, bit: int) -> str:
    return sha16(f"{admit}|{bit}")


def load_seeds(packs_dir: str | Path = "/app/packs") -> list[dict[str, Any]]:
    seeds = []
    for p in sorted(Path(packs_dir).glob("seed_*.json")):
        seeds.append(json.loads(p.read_text(encoding="utf-8")))
    return seeds


def expected_trace(packs_dir: str | Path = "/app/packs", pol_path: str | Path = "/app/docs/pol_a.toml") -> dict[str, Any]:
    """Deterministic coherent trace from packs + policy (oracle-side reference)."""
    pol = load_pol(pol_path)
    alpha = float(pol["alpha"])
    cuts = list(pol["band_cuts"])
    epochs = int(pol["epochs"])
    fence_lag = int(pol["fence_lag"])
    decimals = int(pol["weight_decimals"])
    seeds = load_seeds(packs_dir)

    weights: dict[tuple[str, str], float] = {}
    priors: dict[tuple[str, str], float] = {}
    signals: dict[tuple[str, str], float] = {}
    for seed in seeds:
        sid = seed["id"]
        for it in seed["items"]:
            key = (sid, it["item_id"])
            priors[key] = float(it["prior"])
            signals[key] = float(it["signal"])
            weights[key] = float(it["prior"])

    train_hist: list[tuple[int, str, str]] = []
    rows: list[dict[str, Any]] = []
    wal_depth = 0

    for epoch in range(1, epochs + 1):
        forbidden: set[tuple[str, str]] = set()
        for k, sid, iid in train_hist:
            if epoch - fence_lag <= k <= epoch - 1:
                forbidden.add((sid, iid))

        for seed in sorted(seeds, key=lambda s: s["id"]):
            sid = seed["id"]
            items = list(seed["items"])
            n = len(items)
            train_n = n // 2
            eval_n = n - train_n
            keys = [(sid, it["item_id"]) for it in items]

            candidates = [k for k in keys if k not in forbidden]
            candidates.sort(key=lambda k: (weights[k], k[1]))
            eval_keys = candidates[:eval_n]

            remain = [k for k in keys if k not in eval_keys]
            remain.sort(key=lambda k: (-weights[k], k[1]))
            train_keys = remain[:train_n]

            for key in train_keys:
                w = weights[key]
                band = band_of(w, cuts)
                role = "train"
                bit = 0
                ah = admit_hex(key[0], key[1], epoch, role, band)
                fh = fence_hex(ah, bit)
                rows.append(
                    {
                        "scenario_id": key[0],
                        "epoch": epoch,
                        "item_id": key[1],
                        "band": band,
                        "role": role,
                        "admit_hex": ah,
                        "fence_hex": fh,
                        "weight": float(fmt_weight(w, decimals)),
                    }
                )
                w2 = (1.0 - alpha) * w + alpha * signals[key]
                weights[key] = w2
                train_hist.append((epoch, key[0], key[1]))
                wal_depth += 1

            for key in eval_keys:
                w = weights[key]
                band = band_of(w, cuts)
                role = "eval"
                bit = 1 if key in forbidden else 0
                ah = admit_hex(key[0], key[1], epoch, role, band)
                fh = fence_hex(ah, bit)
                rows.append(
                    {
                        "scenario_id": key[0],
                        "epoch": epoch,
                        "item_id": key[1],
                        "band": band,
                        "role": role,
                        "admit_hex": ah,
                        "fence_hex": fh,
                        "weight": float(fmt_weight(w, decimals)),
                    }
                )
                wal_depth += 1

    admit_sorted = sorted(r["admit_hex"] for r in rows)
    cohort_digest = sha16(",".join(admit_sorted))
    pairs = [f"{k[0]}/{k[1]}:{fmt_weight(weights[k], decimals)}" for k in sorted(weights)]
    resume_digest = sha16(",".join(pairs))
    leaky = any(
        r["role"] == "eval"
        and r["fence_hex"] != fence_hex(r["admit_hex"], 0)
        for r in rows
    )
    # Recompute fence bits properly for status
    fence_status = "sealed"
    # Rebuild forbidden check from rows
    train_by_epoch: dict[int, set[tuple[str, str]]] = {}
    for r in rows:
        if r["role"] == "train":
            train_by_epoch.setdefault(r["epoch"], set()).add((r["scenario_id"], r["item_id"]))
    for r in rows:
        if r["role"] != "eval":
            continue
        e = r["epoch"]
        fset: set[tuple[str, str]] = set()
        for k in range(e - fence_lag, e):
            fset |= train_by_epoch.get(k, set())
        bit = 1 if (r["scenario_id"], r["item_id"]) in fset else 0
        if bit != 0:
            fence_status = "leaky"
            break

    return {
        "rows": rows,
        "summary": {
            "epochs": epochs,
            "rows_total": len(rows),
            "cohort_digest": cohort_digest,
            "resume_digest": resume_digest,
            "fence_status": fence_status,
            "wal_depth": wal_depth,
        },
        "_weights": {f"{k[0]}/{k[1]}": weights[k] for k in weights},
        "_leaky_flag": leaky,
    }


if __name__ == "__main__":
    import pprint

    pprint.pp(expected_trace())
