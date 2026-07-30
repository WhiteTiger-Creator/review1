"""Domain verifier for tactics interrupt resolver."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path("/app/environment")
DATA = ROOT / "data"
KIPS = DATA / "kips"
OUT = Path("/app/output")
TRACE = OUT / "turn_trace.json"
FIELD = OUT / "field_state.json"
JOURNAL = DATA / ".warm" / "journal.jsonl"
BASE = DATA / "scn_base.json"
NOVEL_SCN = DATA / "scn_hold_cross.json"

ARM_KIPS = {
    "nest_chain": "kip_arm_nest",
    "void_mid": "kip_arm_void",
    "phase_board": "kip_arm_phase",
    "snap_paint": "kip_arm_snap",
    "lethal_cut": "kip_arm_lethal",
    "fuse_mix": "kip_arm_fuse",
    "sib_veil": "kip_arm_sib",
}


def _goldens() -> dict:
    return PIN_MAPS


def _nominal() -> dict:
    return PIN_BASE


def _drive(resume: bool = False, all_arms: bool = True) -> None:
    subprocess.run(["/app/environment/exec/tacts", "build"], check=True)
    if resume:
        subprocess.run(["/app/environment/exec/tacts", "play", "--resume"], check=True)
    elif all_arms:
        subprocess.run(["/app/environment/exec/tacts", "play", "--all"], check=True)
    else:
        subprocess.run(["/app/environment/exec/tacts", "play"], check=True)


def _kip_run(name: str) -> None:
    subprocess.run(["/app/environment/exec/tacts", "build"], check=True)
    subprocess.run(["/app/environment/exec/tacts", "play", "--kip", name], check=True)


def _read() -> tuple[dict, dict]:
    assert TRACE.exists(), "turn_trace.json missing"
    assert FIELD.exists(), "field_state.json missing"
    return json.loads(TRACE.read_text()), json.loads(FIELD.read_text())


def _scn(path: Path = BASE) -> dict:
    return json.loads(path.read_text())


def _checksum(wave: int, ids: list[str]) -> str:
    payload = f"{wave}|{','.join(ids)}"
    return subprocess.check_output(
        ["ruby", "-rdigest", "-e", "print Digest::SHA256.hexdigest(ARGV[0])", payload],
        text=True,
    ).strip()


def _causal_ok(rows: list[dict]) -> bool:
    seen: set[str] = set()
    for row in rows:
        pid = row["pid"]
        if pid is not None and pid not in seen:
            return False
        seen.add(row["id"])
    return True


def _ladder_arms() -> list[tuple[str, str]]:
    arms: list[tuple[str, str]] = []
    name = None
    for line in (DATA / "ladder.toml").read_text().splitlines():
        line = line.strip()
        if line.startswith("name"):
            _, _, raw = line.partition("=")
            name = raw.strip().strip('"')
        elif line.startswith("file") and name:
            _, _, raw = line.partition("=")
            file_name = raw.strip().strip('"')
            arms.append((name, file_name))
            name = None
    return arms


def _arm_artifacts(name: str) -> tuple[dict, dict]:
    side = DATA / ".warm" / f"arm_{name}"
    tr = json.loads((side / "turn_trace.json").read_text())
    fs = json.loads((side / "field_state.json").read_text())
    return tr, fs


def _pos(ids: list[str], needle: str) -> int:
    for i, value in enumerate(ids):
        if value == needle:
            return i
    raise AssertionError(f"missing {needle}")


def _kip_pack(stem: str) -> dict:
    return json.loads((KIPS / f"{stem}.json").read_text())


def _kip_artifacts(stem: str) -> tuple[dict, dict]:
    side = DATA / ".warm" / stem
    tr = json.loads((side / "turn_trace.json").read_text())
    fs = json.loads((side / "field_state.json").read_text())
    return tr, fs


def _match_pin(tr: dict, fs: dict, pin: dict) -> None:
    assert [r["id"] for r in tr["rows"]] == pin["row_ids"]
    for rid, pid in pin["pids"].items():
        row = next(r for r in tr["rows"] if r["id"] == rid)
        assert row["pid"] == pid
    assert fs["actors"] == pin["actors"]
    assert fs["tiles"] == pin["tiles"]


def _play_scn(scn: dict, stem: str) -> tuple[dict, dict]:
    warm = DATA / ".warm"
    warm.mkdir(parents=True, exist_ok=True)
    scn_path = warm / f"{stem}_scn.json"
    scn_path.write_text(json.dumps(scn) + "\n")
    side = warm / stem
    side.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/app/environment/exec/tacts", "build"], check=True)
    # Drive via kip-shaped temp pack so play --kip works without env pin maps.
    pack_path = KIPS / f"{stem}.json"
    packed = False
    if not pack_path.exists():
        pack_path.write_text(json.dumps({"blurb": "verifier holdout", "scn": scn}) + "\n")
        packed = True
    try:
        subprocess.run(["/app/environment/exec/tacts", "play", "--kip", stem], check=True)
        return _kip_artifacts(stem)
    finally:
        if packed and pack_path.exists():
            pack_path.unlink()


@pytest.fixture(autouse=True)
def _fresh_round():
    """Rebuild and replay before every test so cases never share round state."""
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    if JOURNAL.exists():
        JOURNAL.unlink()
    _drive()
    yield


def test_q01_shape():
    """Transcript and final-state schema fields are present and typed; checksum matches desk reduction."""
    tr, fs = _read()
    assert "wave" in tr and "rows" in tr
    assert isinstance(tr["rows"], list)
    assert len(tr["rows"]) >= 1
    for row in tr["rows"]:
        for key in ("id", "kind", "actor", "target", "pid", "slot"):
            assert key in row
        assert isinstance(row["id"], str)
        assert isinstance(row["kind"], str)
        assert isinstance(row["actor"], str)
        assert row["target"] is None or isinstance(row["target"], str)
        assert row["pid"] is None or isinstance(row["pid"], str)
        assert isinstance(row["slot"], int)
    assert "wave" in fs and "actors" in fs and "tiles" in fs and "checksum" in fs
    assert fs["wave"] == tr["wave"]
    assert len(fs["checksum"]) == 64
    for body in fs["actors"].values():
        assert "hp" in body and "pos" in body
    for body in fs["tiles"].values():
        assert "mod" in body
    ids = [r["id"] for r in tr["rows"]]
    assert fs["checksum"] == _checksum(int(tr["wave"]), ids)
    assert _causal_ok(tr["rows"])


def test_q02_seq():
    """Nominal primary order matches desk ranking and omits void jobs."""
    tr, _ = _read()
    ids = [r["id"] for r in tr["rows"]]
    pin = _nominal()
    assert ids == pin["row_ids"]
    scn = _scn()
    voided_jobs = {j["id"] for j in scn["jobs"] if j.get("void")}
    assert [x for x in voided_jobs if x in set(ids)] == []


def test_q03_pick():
    """Equal-init ranking matches kip_rank obligations."""
    pack = _kip_pack("kip_rank")
    _kip_run("kip_rank")
    tr, fs = _kip_artifacts("kip_rank")
    _match_pin(tr, fs, _goldens()["kip_rank"])
    voided = {j["id"] for j in pack["scn"]["jobs"] if j.get("void")}
    assert [x for x in voided if x in {r["id"] for r in tr["rows"]}] == []


def test_q04_nest():
    """Reaction rows nest under the parent and resolve before later primaries."""
    tr, _ = _read()
    ids = [r["id"] for r in tr["rows"]]
    rows = {r["id"]: r for r in tr["rows"]}
    scn = _scn()
    parent = next(j["id"] for j in scn["jobs"] if j["kind"] == "strike" and not j.get("void"))
    target = next(j["target"] for j in scn["jobs"] if j["id"] == parent)
    hooks = [h["id"] for h in scn["hooks"] if not h.get("void") and h["vs"] == target]
    assert rows[hooks[0]]["pid"] == parent
    assert rows[hooks[1]]["pid"] == parent
    assert _pos(ids, parent) < _pos(ids, hooks[0]) < _pos(ids, hooks[1])
    nxt = next(j["id"] for j in scn["jobs"] if j["kind"] == "delay")
    assert _pos(ids, hooks[1]) < _pos(ids, nxt)


def test_q05_undo():
    """Voided hooks leave no transcript row; nominal maps match desk outcomes."""
    tr, fs = _read()
    scn = _scn()
    pin = _nominal()
    voided = {h["id"] for h in scn["hooks"] if h.get("void")}
    ids = {r["id"] for r in tr["rows"]}
    assert [x for x in voided if x in ids] == []
    assert fs["actors"] == pin["actors"]
    assert fs["tiles"] == pin["tiles"]


def test_q06_span():
    """Holdout nest arm matches nest_chain obligations."""
    name, _file_name = _ladder_arms()[0]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])
    assert _causal_ok(tr["rows"])


def test_q07_void_arm():
    """Holdout void arm matches void_mid obligations."""
    name, _file_name = _ladder_arms()[1]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])
    arm_scn = _scn(DATA / _file_name)
    voided = {h["id"] for h in arm_scn["hooks"] if h.get("void")}
    assert [x for x in voided if x in {r["id"] for r in tr["rows"]}] == []


def test_q08_wave():
    """Delayed fire lands between its delay job and the next primary."""
    tr, fs = _read()
    ids = [r["id"] for r in tr["rows"]]
    scn = _scn()
    pin = _nominal()
    delay = next(j for j in scn["jobs"] if j["kind"] == "delay")
    fire_id = f"{delay['id']}#fire"
    last = pin["row_ids"][-1]
    assert _pos(ids, delay["id"]) < _pos(ids, fire_id) < _pos(ids, last)
    fire = next(r for r in tr["rows"] if r["id"] == fire_id)
    assert fire["kind"] == "delay_fire"
    assert fire["pid"] == delay["id"]
    assert fs["actors"] == pin["actors"]


def test_q09_grid():
    """Holdout phase arm matches phase_board obligations."""
    name, _file_name = _ladder_arms()[2]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])
    arm = _scn(DATA / _file_name)
    void_delay = next(j for j in arm["jobs"] if j.get("void"))
    assert void_delay["id"] not in {r["id"] for r in tr["rows"]}
    assert f"{void_delay['id']}#fire" not in {r["id"] for r in tr["rows"]}


def test_q10_resume():
    """Mid-round journal resume converges; leftover poison journal is ignored by clean play."""
    tr0, fs0 = _read()
    lines = JOURNAL.read_text().splitlines()
    assert len(lines) >= 2
    keep: list[str] = []
    for line in lines:
        row = json.loads(line)
        if row["pid"] is None and keep:
            break
        keep.append(line)
    assert keep
    JOURNAL.write_text("\n".join(keep) + "\n")
    _drive(resume=True, all_arms=False)
    tr1, fs1 = _read()
    assert tr1 == tr0
    assert fs1 == fs0
    JOURNAL.write_text(
        json.dumps(
            {
                "id": "__stale__",
                "kind": "move",
                "actor": "a1",
                "target": None,
                "pid": None,
                "slot": 0,
            }
        )
        + "\n"
    )
    _drive(resume=False, all_arms=False)
    tr2, fs2 = _read()
    nom = _nominal()
    assert [r["id"] for r in tr2["rows"]] == nom["row_ids"]
    assert fs2["actors"] == nom["actors"]
    assert "__stale__" not in {r["id"] for r in tr2["rows"]}


def test_q11_snap():
    """Holdout snap arm matches snap_paint obligations."""
    name, _file_name = _ladder_arms()[3]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])


def test_q12_lethal():
    """Holdout lethal arm matches lethal_cut obligations."""
    name, _file_name = _ladder_arms()[4]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])


def test_q13_fuse():
    """Composed fuse arm matches fuse_mix obligations."""
    name, _file_name = _ladder_arms()[5]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])
    arm = _scn(DATA / _file_name)
    void_job = next(j for j in arm["jobs"] if j.get("void"))
    void_hook = next(h for h in arm["hooks"] if h.get("void"))
    ids = {r["id"] for r in tr["rows"]}
    assert void_job["id"] not in ids
    assert void_hook["id"] not in ids


def test_q17_sib():
    """Sibling paint under an open parent must not revise later nested strike damage."""
    name, _file_name = _ladder_arms()[6]
    tr, fs = _arm_artifacts(name)
    _match_pin(tr, fs, _goldens()[ARM_KIPS[name]])
    assert _causal_ok(tr["rows"])
    assert fs["checksum"] == _checksum(int(tr["wave"]), [r["id"] for r in tr["rows"]])


def test_q14_twin():
    """Consecutive plays emit byte-identical artifacts; wave mutate drifts checksum only."""
    tr1, fs1 = _read()
    _drive()
    tr2, fs2 = _read()
    assert tr1 == tr2
    assert fs1 == fs2
    dig0 = fs1["checksum"]
    nom = _nominal()
    backup = BASE.read_text()
    try:
        scn = json.loads(backup)
        scn["wave"] = int(scn["wave"]) + 11
        BASE.write_text(json.dumps(scn, indent=2) + "\n")
        _drive()
        tr3, fs3 = _read()
        assert fs3["checksum"] != dig0
        assert fs3["wave"] == scn["wave"]
        assert [r["id"] for r in tr3["rows"]] == nom["row_ids"]
        assert fs3["actors"] == nom["actors"]
        assert fs3["tiles"] == nom["tiles"]
        assert fs3["checksum"] == _checksum(scn["wave"], nom["row_ids"])
    finally:
        BASE.write_text(backup)
        _drive()


def test_q15_seal():
    """Checksum matches the published reduction; causal parents form a tree."""
    tr, fs = _read()
    ids = [r["id"] for r in tr["rows"]]
    digest = _checksum(int(tr["wave"]), ids)
    assert fs["checksum"] == digest
    assert _causal_ok(tr["rows"])
    nom = _nominal()
    assert ids == nom["row_ids"]
    assert fs["actors"] == nom["actors"]
    for row in tr["rows"]:
        if row["pid"] is not None:
            assert row["pid"] in ids


def test_q16_packs():
    """Every worked pack replays to its pinned obligations."""
    stems = sorted(p.stem for p in KIPS.glob("kip_*.json"))
    assert len(stems) >= 6
    g = _goldens()
    for stem in stems:
        _kip_run(stem)
        tr, fs = _kip_artifacts(stem)
        _match_pin(tr, fs, g[stem])
        assert _causal_ok(tr["rows"])
        assert fs["checksum"] == _checksum(int(tr["wave"]), [r["id"] for r in tr["rows"]])


def test_q18_novel_cross():
    """Composed hold-cross scenario: frame seal, void omit, delay fire, and ranking jointly."""
    scn = json.loads(NOVEL_SCN.read_text())
    tr, fs = _play_scn(scn, "_hold_cross")
    pin = PIN_NOVEL
    _match_pin(tr, fs, pin)
    assert _causal_ok(tr["rows"])
    assert fs["checksum"] == _checksum(int(tr["wave"]), [r["id"] for r in tr["rows"]])
    ids = {r["id"] for r in tr["rows"]}
    void_jobs = {j["id"] for j in scn["jobs"] if j.get("void")}
    void_hooks = {h["id"] for h in scn["hooks"] if h.get("void")}
    assert [x for x in void_jobs if x in ids] == []
    assert [x for x in void_hooks if x in ids] == []
    delay = next(j for j in scn["jobs"] if j["kind"] == "delay")
    assert f"{delay['id']}#fire" in ids

# Name-bound so single-id pins are not parsed as output-key subscripts.
_PIN_VOID_ARM = "vj1"
_PIN_VOID_PACK = "vs"
_PIN_IDS_0 = [_PIN_VOID_ARM]
_PIN_IDS_1 = [_PIN_VOID_PACK]

PIN_MAPS = {
  "kip_arm_fuse": {
    "row_ids": [
      "z0",
      "z1",
      "zh1",
      "zh2",
      "z0#fire"
    ],
    "pids": {
      "z0": None,
      "z1": None,
      "zh1": "z1",
      "zh2": "zh1",
      "z0#fire": "z0"
    },
    "actors": {
      "f1": {
        "hp": 19,
        "pos": "p1"
      },
      "f2": {
        "hp": -1,
        "pos": "p2"
      },
      "f3": {
        "hp": 20,
        "pos": "p3"
      }
    },
    "tiles": {
      "p1": {
        "mod": 7
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_arm_lethal": {
    "row_ids": [
      "m2",
      "m2#fire",
      "m1",
      "lh1"
    ],
    "pids": {
      "m2": None,
      "m2#fire": "m2",
      "m1": None,
      "lh1": "m1"
    },
    "actors": {
      "l1": {
        "hp": 19,
        "pos": "p1"
      },
      "l2": {
        "hp": -2,
        "pos": "p2"
      },
      "l3": {
        "hp": 20,
        "pos": "p3"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_arm_nest": {
    "row_ids": [
      "n1",
      "nh1",
      "nh2"
    ],
    "pids": {
      "n1": None,
      "nh1": "n1",
      "nh2": "nh1"
    },
    "actors": {
      "b1": {
        "hp": 19,
        "pos": "p1"
      },
      "b2": {
        "hp": 18,
        "pos": "p2"
      },
      "b3": {
        "hp": 19,
        "pos": "p3"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_arm_phase": {
    "row_ids": [
      "g1",
      "g2"
    ],
    "pids": {
      "g1": None,
      "g2": None
    },
    "actors": {
      "d1": {
        "hp": 15,
        "pos": "p1"
      },
      "d2": {
        "hp": 15,
        "pos": "p3"
      },
      "d3": {
        "hp": 15,
        "pos": "p3"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 2
      }
    }
  },
  "kip_arm_sib": {
    "row_ids": [
      "q1",
      "qh1",
      "qh2"
    ],
    "pids": {
      "q1": None,
      "qh1": "q1",
      "qh2": "q1"
    },
    "actors": {
      "u1": {
        "hp": 17,
        "pos": "p1"
      },
      "u2": {
        "hp": 18,
        "pos": "p1"
      },
      "u3": {
        "hp": 20,
        "pos": "p1"
      }
    },
    "tiles": {
      "p1": {
        "mod": 7
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_arm_snap": {
    "row_ids": [
      "k1",
      "ph1"
    ],
    "pids": {
      "k1": None,
      "ph1": "k1"
    },
    "actors": {
      "s1": {
        "hp": 20,
        "pos": "p1"
      },
      "s2": {
        "hp": 18,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 9
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_arm_void": {
    "row_ids": _PIN_IDS_0,
    "pids": {
      "vj1": None
    },
    "actors": {
      "c1": {
        "hp": 10,
        "pos": "p1"
      },
      "c2": {
        "hp": 8,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_delay": {
    "row_ids": [
      "dd",
      "dd#fire",
      "dm"
    ],
    "pids": {
      "dd": None,
      "dd#fire": "dd",
      "dm": None
    },
    "actors": {
      "d1": {
        "hp": 10,
        "pos": "p1"
      },
      "d2": {
        "hp": 8,
        "pos": "p1"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_kill": {
    "row_ids": [
      "ks",
      "kk"
    ],
    "pids": {
      "ks": None,
      "kk": "ks"
    },
    "actors": {
      "k1": {
        "hp": 20,
        "pos": "p1"
      },
      "k2": {
        "hp": -2,
        "pos": "p2"
      },
      "k3": {
        "hp": 20,
        "pos": "p1"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_nest": {
    "row_ids": [
      "ns",
      "nh"
    ],
    "pids": {
      "ns": None,
      "nh": "ns"
    },
    "actors": {
      "n1": {
        "hp": 9,
        "pos": "p1"
      },
      "n2": {
        "hp": 8,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_pid": {
    "row_ids": [
      "pd",
      "pd#fire",
      "ps",
      "ph"
    ],
    "pids": {
      "pd": None,
      "pd#fire": "pd",
      "ps": None,
      "ph": "ps"
    },
    "actors": {
      "p1a": {
        "hp": 11,
        "pos": "p1"
      },
      "p2a": {
        "hp": 10,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_rank": {
    "row_ids": [
      "r1",
      "r2",
      "r0"
    ],
    "pids": {
      "r1": None,
      "r2": None,
      "r0": None
    },
    "actors": {
      "u1": {
        "hp": 10,
        "pos": "p2"
      },
      "u2": {
        "hp": 10,
        "pos": "p1"
      },
      "u3": {
        "hp": 10,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_sib": {
    "row_ids": [
      "q1",
      "qh1",
      "qh2"
    ],
    "pids": {
      "q1": None,
      "qh1": "q1",
      "qh2": "q1"
    },
    "actors": {
      "u1": {
        "hp": 17,
        "pos": "p1"
      },
      "u2": {
        "hp": 18,
        "pos": "p1"
      },
      "u3": {
        "hp": 20,
        "pos": "p1"
      }
    },
    "tiles": {
      "p1": {
        "mod": 7
      },
      "p2": {
        "mod": 0
      },
      "p3": {
        "mod": 0
      }
    }
  },
  "kip_snap": {
    "row_ids": [
      "ss",
      "sp"
    ],
    "pids": {
      "ss": None,
      "sp": "ss"
    },
    "actors": {
      "s1": {
        "hp": 20,
        "pos": "p1"
      },
      "s2": {
        "hp": 18,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 9
      },
      "p2": {
        "mod": 0
      }
    }
  },
  "kip_void": {
    "row_ids": _PIN_IDS_1,
    "pids": {
      "vs": None
    },
    "actors": {
      "v1": {
        "hp": 9,
        "pos": "p1"
      },
      "v2": {
        "hp": 8,
        "pos": "p2"
      }
    },
    "tiles": {
      "p1": {
        "mod": 0
      },
      "p2": {
        "mod": 0
      }
    }
  }
}

PIN_BASE = {
  "row_ids": [
    "j1",
    "h1",
    "h3",
    "j2",
    "j2#fire",
    "j3"
  ],
  "pids": {
    "j1": None,
    "h1": "j1",
    "h3": "j1",
    "j2": None,
    "j2#fire": "j2",
    "j3": None
  },
  "actors": {
    "a1": {
      "hp": 9,
      "pos": "p1"
    },
    "a2": {
      "hp": 10,
      "pos": "p2"
    },
    "a3": {
      "hp": 11,
      "pos": "p2"
    }
  },
  "tiles": {
    "p1": {
      "mod": 4
    },
    "p2": {
      "mod": 1
    },
    "p3": {
      "mod": 0
    },
    "p4": {
      "mod": 0
    }
  }
}

PIN_NOVEL = {
  "row_ids": [
    "c1",
    "ch2",
    "ch1",
    "c2",
    "c2#fire",
    "c5",
    "ch4",
    "c4"
  ],
  "pids": {
    "c1": None,
    "ch2": "c1",
    "ch1": "c1",
    "c2": None,
    "c2#fire": "c2",
    "c5": None,
    "ch4": "c5",
    "c4": None
  },
  "actors": {
    "x1": {
      "hp": 16,
      "pos": "p1"
    },
    "x2": {
      "hp": 1,
      "pos": "p2"
    },
    "x3": {
      "hp": 13,
      "pos": "p1"
    },
    "x4": {
      "hp": 10,
      "pos": "p1"
    }
  },
  "tiles": {
    "p1": {
      "mod": 8
    },
    "p2": {
      "mod": 5
    },
    "p3": {
      "mod": 1
    }
  }
}
