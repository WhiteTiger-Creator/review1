import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path("/app")
SRC = ROOT / "main.go"
BIN = ROOT / "bin" / "crystal-orbit-inventory"
BASE = ROOT / "task_file" / "case.json"


@pytest.fixture(scope="session", autouse=True)
def compile_agent():
    """The submitted Go source builds with the exact public reproducible command."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["go", "build", "-trimpath", "-ldflags=-buildid=", "-o", str(BIN), str(SRC)],
        capture_output=True,
        text=True,
    check=False,
    )
    assert p.returncode == 0, p.stderr


def invoke(case, root):
    root.mkdir(parents=True, exist_ok=True)
    ip = root / "case.json"
    op = root / "nested" / "result.json"
    ip.write_text(json.dumps(case, separators=(",", ":")) + "\n")
    p = subprocess.run(
        [str(BIN), "--input", str(ip.resolve()), "--output", str(op.resolve())],
        capture_output=True,
        text=True,
    check=False,
    )
    return p, op, ip


def determinant(m):
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def reference(c):
    d = c["denominator"]
    occupancy = {}
    rows = []
    for site in sorted(c["sites"], key=lambda x: x["id"]):
        points = []
        stabilizer = 0
        for op in c["operations"]:
            point = tuple(
                (
                    sum(op["matrix"][i][j] * site["coordinate"][j] for j in range(3))
                    + op["shift"][i]
                )
                % d
                for i in range(3)
            )
            points.append(point)
            stabilizer += point == tuple(site["coordinate"])
        unique = sorted(set(points))
        positions = [f"{x}/{d},{y}/{d},{z}/{d}" for x, y, z in unique]
        for point in unique:
            occupancy.setdefault(point, set()).add(site["id"])
        rows.append(
            {
                "id": site["id"],
                "species": site["species"],
                "multiplicity": len(unique),
                "stabilizer": stabilizer,
                "positions": positions,
            },
        )
    collisions = [
        {
            "position": f"{x}/{d},{y}/{d},{z}/{d}",
            "site_ids": sorted(occupancy[(x, y, z)]),
        }
        for x, y, z in sorted(k for k, v in occupancy.items() if len(v) > 1)
    ]
    return {
        "sites": rows,
        "collisions": collisions,
        "operation_count": len(c["operations"]),
    }


def test_exact_orbits_stabilizers_multiplicities_and_cross_site_collisions(tmp_path):
    """Bundled rational symmetries produce exact independently expanded orbits, stabilizers, and collision membership."""
    c = json.loads(BASE.read_text())
    p, o, _ = invoke(c, tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(o.read_text()) == reference(c)


def test_changed_denominator_shifted_operations_and_reordered_sites(tmp_path):
    """A renamed fifth-coordinate structure with shifts and axis rotation is recomputed without positional assumptions."""
    c = {
        "denominator": 5,
        "sites": [
            {"id": "beta", "species": "B", "coordinate": [4, 1, 0]},
            {"id": "alpha", "species": "A", "coordinate": [1, 2, 3]},
        ],
        "operations": [
            {
                "id": "rot",
                "matrix": [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
                "shift": [1, 0, 2],
            },
            {
                "id": "identity",
                "matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "shift": [0, 0, 0],
            },
            {
                "id": "mirror",
                "matrix": [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "shift": [2, 0, 0],
            },
        ],
    }
    p, o, _ = invoke(c, tmp_path)
    assert p.returncode == 0, p.stderr
    assert json.loads(o.read_text()) == reference(c)


def test_singular_duplicate_missing_identity_and_argv_cleanup(tmp_path):
    """Invalid determinant, duplicate affine operation, missing identity, and reversed flags remove stale outputs."""
    variants = []
    c = json.loads(BASE.read_text())
    c["operations"][1]["matrix"] = [[1, 0, 0], [0, 0, 0], [0, 0, 1]]
    variants.append(c)
    c = json.loads(BASE.read_text())
    c["operations"].append(dict(c["operations"][0], id="duplicate"))
    variants.append(c)
    c = json.loads(BASE.read_text())
    c["operations"] = c["operations"][1:]
    variants.append(c)
    for n, c in enumerate(variants):
        p, o, _ = invoke(c, tmp_path / str(n))
        assert (
            p.returncode != 0 and not o.exists() and not Path(str(o) + ".tmp").exists()
        )
    c = json.loads(BASE.read_text())
    p, o, i = invoke(c, tmp_path / "argv")
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text("x")
    p = subprocess.run(
        [str(BIN), "--output", str(o.resolve()), "--input", str(i.resolve())],
    check=False,
    )
    assert p.returncode != 0 and not o.exists()


def test_deterministic_atomic_replacement_and_input_immutability(tmp_path):
    """Repeated orbit inventories replace stale output byte-identically and preserve the coordinate source."""
    c = json.loads(BASE.read_text())
    p, o, i = invoke(c, tmp_path)
    assert p.returncode == 0
    want = o.read_bytes()
    before = i.read_bytes()
    o.write_text("old")
    p = subprocess.run(
        [str(BIN), "--input", str(i.resolve()), "--output", str(o.resolve())],
    check=False,
    )
    assert p.returncode == 0 and o.read_bytes() == want and i.read_bytes() == before
