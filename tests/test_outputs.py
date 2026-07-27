"""Exact checks for a rank-four oriented-matroid face-incidence census.

The reference census is derived from integer orientation determinants in R^4.
It merges all affine-independent four-point carriers that produce the same
complete coplanar face, excludes interior points, sorts facet incidence rows,
and audits the resulting face lattice through incidence and carrier-sign hashes.
"""

import functools
import itertools
import math
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

HASH_MOD = 1_000_000_007
HASH_BASE = 1_000_003


def determinant(matrix):
    if len(matrix) == 1:
        return matrix[0][0]
    return sum((-1) ** col * matrix[0][col] * determinant([row[:col] + row[col + 1:] for row in matrix[1:]]) for col in range(len(matrix)))


def orient(a, b, c, d, q):
    return determinant([[p[j] - a[j] for j in range(4)] for p in (b, c, d, q)])


def hyperplane_coefficients(points, ids):
    rows = [[*points[i], 1] for i in ids]
    coeffs = []
    for col in range(5):
        submatrix = [row[:col] + row[col + 1:] for row in rows]
        coeffs.append(((-1) ** col) * determinant(submatrix))
    return tuple(coeffs)


def primitive_carrier(points, ids):
    coeffs = hyperplane_coefficients(points, ids)
    values = [sum(c * x for c, x in zip(coeffs[:4], q)) + coeffs[4] for q in points]
    if not any(values):
        return None
    if any(v > 0 for v in values) and any(v < 0 for v in values):
        return None
    if any(v < 0 for v in values):
        coeffs = tuple(-c for c in coeffs)
    scale = 0
    for value in coeffs:
        scale = math.gcd(scale, abs(value))
    return tuple(value // scale for value in coeffs)


def affine_dimension(points, ids):
    if len(ids) <= 1:
        return 0
    base = points[ids[0]]
    differences = [
        tuple(points[index][axis] - base[axis] for axis in range(4))
        for index in ids[1:]
    ]
    for rank in range(min(4, len(differences)), 0, -1):
        for rows in itertools.combinations(differences, rank):
            for columns in itertools.combinations(range(4), rank):
                matrix = [[row[column] for column in columns] for row in rows]
                if determinant(matrix) != 0:
                    return rank
    return 0


def complete_face_family(points, hull, ordered_facets):
    if not ordered_facets:
        return []
    faces = {tuple(hull), *ordered_facets}
    changed = True
    while changed:
        changed = False
        snapshot = tuple(faces)
        for left, right in itertools.combinations(snapshot, 2):
            face = tuple(sorted(set(left) & set(right)))
            if face and face not in faces:
                faces.add(face)
                changed = True
    return sorted(faces, key=lambda face: (affine_dimension(points, face), face))


@functools.cache
def reference_facet_profile(points):
    facets = {}
    for i, j, k, m in itertools.combinations(range(len(points)), 4):
        carrier = primitive_carrier(points, (i, j, k, m))
        if carrier is None:
            continue
        facet = tuple(q for q, point in enumerate(points) if sum(c * x for c, x in zip(carrier[:4], point)) + carrier[4] == 0)
        facets.setdefault(facet, carrier)
    hull = sorted({q for facet in facets for q in facet})
    hull_line = "HULL " + str(len(hull))
    if hull:
        hull_line += " " + " ".join(str(q + 1) for q in hull)
    lines = [hull_line, f"FACETS {len(facets)}"]
    lines.extend("FACET " + str(len(facet)) + " " + " ".join(str(q + 1) for q in facet) for facet in sorted(facets))
    facet_hash = 17
    for facet in sorted(facets):
        for value in (len(facet), *(q + 1 for q in facet)):
            facet_hash = (facet_hash * HASH_BASE + value) % HASH_MOD
    triple_face_hash = 31
    for triple in itertools.combinations(hull, 3):
        count = sum(all(vertex in facet for vertex in triple) for facet in facets)
        for value in (*(q + 1 for q in triple), count):
            triple_face_hash = (triple_face_hash * HASH_BASE + value) % HASH_MOD
    normal_hash = 43
    for facet in sorted(facets):
        carrier = facets[facet]
        for value in (len(facet), *(q + 1 for q in facet), *carrier):
            normal_hash = (normal_hash * HASH_BASE + (value % HASH_MOD)) % HASH_MOD
    pair_normal_hash = 83
    ordered_facets = sorted(facets)
    for left_index, left in enumerate(ordered_facets):
        for right_index, right in enumerate(ordered_facets[left_index + 1 :], start=left_index + 1):
            face = tuple(sorted(set(left) & set(right)))
            if len(face) < 2:
                continue
            for value in (
                left_index + 1,
                right_index + 1,
                len(face),
                *(q + 1 for q in face),
                *facets[left],
                *facets[right],
            ):
                pair_normal_hash = (
                    pair_normal_hash * HASH_BASE + (value % HASH_MOD)
                ) % HASH_MOD
    intersection_faces = set()
    for left, right in itertools.combinations(ordered_facets, 2):
        face = tuple(sorted(set(left) & set(right)))
        if len(face) >= 2:
            intersection_faces.add(face)
    intersection_hash = 59
    for face in sorted(intersection_faces):
        containing = sum(all(vertex in facet for vertex in face) for facet in facets)
        for value in (len(face), *(q + 1 for q in face), containing):
            intersection_hash = (intersection_hash * HASH_BASE + value) % HASH_MOD
    carrier_sign_hash = 71
    for ids in itertools.combinations(range(len(points)), 4):
        coeffs = hyperplane_coefficients(points, ids)
        if not any(coeffs):
            continue
        values = [sum(c * x for c, x in zip(coeffs[:4], point)) + coeffs[4] for point in points]
        first_nonzero = next((value for value in values if value != 0), None)
        if first_nonzero is None:
            continue
        if first_nonzero < 0:
            values = [-value for value in values]
        for value in (*(q + 1 for q in ids),):
            carrier_sign_hash = (carrier_sign_hash * HASH_BASE + value) % HASH_MOD
        for value in values:
            sign_code = 0 if value < 0 else 1 if value == 0 else 2
            carrier_sign_hash = (carrier_sign_hash * HASH_BASE + sign_code) % HASH_MOD
    vertex_figure_hash = 97
    for vertex in hull:
        incident = [
            position + 1
            for position, facet in enumerate(ordered_facets)
            if vertex in facet
        ]
        for value in (vertex + 1, len(incident), *incident):
            vertex_figure_hash = (vertex_figure_hash * HASH_BASE + value) % HASH_MOD
        for left_pos, right_pos in itertools.combinations(incident, 2):
            left = ordered_facets[left_pos - 1]
            right = ordered_facets[right_pos - 1]
            face = tuple(sorted(set(left) & set(right)))
            for value in (left_pos, right_pos, len(face), *(q + 1 for q in face)):
                vertex_figure_hash = (vertex_figure_hash * HASH_BASE + value) % HASH_MOD
    facet_triple_hash = 109
    for a, b, c in itertools.combinations(range(len(ordered_facets)), 3):
        face = tuple(
            sorted(
                set(ordered_facets[a])
                & set(ordered_facets[b])
                & set(ordered_facets[c])
            )
        )
        if not face:
            continue
        containing = sum(all(vertex in facet for vertex in face) for facet in facets)
        for value in (a + 1, b + 1, c + 1, len(face), *(q + 1 for q in face), containing):
            facet_triple_hash = (facet_triple_hash * HASH_BASE + value) % HASH_MOD
    facet_quad_hash = 127
    for a, b, c, d in itertools.combinations(range(len(ordered_facets)), 4):
        face = tuple(
            sorted(
                set(ordered_facets[a])
                & set(ordered_facets[b])
                & set(ordered_facets[c])
                & set(ordered_facets[d])
            )
        )
        if not face:
            continue
        containing = sum(all(vertex in facet for vertex in face) for facet in facets)
        for value in (a + 1, b + 1, c + 1, d + 1, len(face), *(q + 1 for q in face), containing):
            facet_quad_hash = (facet_quad_hash * HASH_BASE + value) % HASH_MOD
    face_family = complete_face_family(points, hull, tuple(ordered_facets))
    face_lattice_hash = 149
    dimensions = []
    for face in face_family:
        dimension = affine_dimension(points, face)
        dimensions.append(dimension)
        containing = sum(all(vertex in facet for vertex in face) for facet in facets)
        for value in (
            dimension,
            len(face),
            *(vertex + 1 for vertex in face),
            containing,
        ):
            face_lattice_hash = (
                face_lattice_hash * HASH_BASE + value
            ) % HASH_MOD
    flag_hash = 163
    positions_by_dimension = {
        dimension: [
            position
            for position, actual_dimension in enumerate(dimensions)
            if actual_dimension == dimension
        ]
        for dimension in range(4)
    }
    for p0 in positions_by_dimension[0]:
        face0 = set(face_family[p0])
        for p1 in positions_by_dimension[1]:
            face1 = set(face_family[p1])
            if not face0 < face1:
                continue
            for p2 in positions_by_dimension[2]:
                face2 = set(face_family[p2])
                if not face1 < face2:
                    continue
                for p3 in positions_by_dimension[3]:
                    face3 = set(face_family[p3])
                    if not face2 < face3:
                        continue
                    for value in (p0 + 1, p1 + 1, p2 + 1, p3 + 1):
                        flag_hash = (flag_hash * HASH_BASE + value) % HASH_MOD
    facet_carrier_hash = 181
    for position, facet in enumerate(ordered_facets, start=1):
        normal = facets[facet]
        for value in (
            position,
            len(facet),
            *(vertex + 1 for vertex in facet),
            *normal,
        ):
            facet_carrier_hash = (
                facet_carrier_hash * HASH_BASE + value
            ) % HASH_MOD
        for ids in itertools.combinations(facet, 4):
            for value in (vertex + 1 for vertex in ids):
                facet_carrier_hash = (
                    facet_carrier_hash * HASH_BASE + value
                ) % HASH_MOD
            carrier = hyperplane_coefficients(points, ids)
            scale = 0
            for value in carrier:
                scale = math.gcd(scale, abs(value))
            if scale == 0:
                facet_carrier_hash = (
                    facet_carrier_hash * HASH_BASE
                ) % HASH_MOD
                continue
            carrier = tuple(value // scale for value in carrier)
            pivot = next(index for index, value in enumerate(normal) if value)
            if (carrier[pivot] < 0) != (normal[pivot] < 0):
                carrier = tuple(-value for value in carrier)
            facet_carrier_hash = (
                facet_carrier_hash * HASH_BASE + 1
            ) % HASH_MOD
            for value in carrier:
                facet_carrier_hash = (
                    facet_carrier_hash * HASH_BASE + value
                ) % HASH_MOD
    face_positions = {
        face: position
        for position, face in enumerate(face_family, start=1)
    }
    facet_sets = tuple(set(facet) for facet in ordered_facets)
    containing_cache = {}

    def containing_positions(face):
        if face not in containing_cache:
            face_set = set(face)
            containing_cache[face] = tuple(
                position
                for position, facet_set in enumerate(facet_sets, start=1)
                if face_set <= facet_set
            )
        return containing_cache[face]

    face_normal_hash = 191
    for position, (face, dimension) in enumerate(
        zip(face_family, dimensions), start=1
    ):
        containing = containing_positions(face)
        for value in (
            position,
            dimension,
            len(face),
            *(vertex + 1 for vertex in face),
            len(containing),
            *containing,
        ):
            face_normal_hash = (
                face_normal_hash * HASH_BASE + value
            ) % HASH_MOD
        for facet_position in containing:
            for value in facets[ordered_facets[facet_position - 1]]:
                face_normal_hash = (
                    face_normal_hash * HASH_BASE + value
                ) % HASH_MOD
    normal_gram_hash = 193
    for left, right in itertools.combinations(range(len(ordered_facets)), 2):
        left_facet = ordered_facets[left]
        right_facet = ordered_facets[right]
        face = tuple(sorted(set(left_facet) & set(right_facet)))
        if not face:
            continue
        left_normal = facets[left_facet][:4]
        right_normal = facets[right_facet][:4]
        left_norm = sum(value * value for value in left_normal)
        right_norm = sum(value * value for value in right_normal)
        inner = sum(
            left_value * right_value
            for left_value, right_value in zip(left_normal, right_normal)
        )
        gram = left_norm * right_norm - inner * inner
        for value in (
            left + 1,
            right + 1,
            face_positions[face],
            len(face),
            *(vertex + 1 for vertex in face),
            left_norm,
            right_norm,
            inner,
            gram,
        ):
            normal_gram_hash = (
                normal_gram_hash * HASH_BASE + value
            ) % HASH_MOD
    facet_positions = {
        facet: position
        for position, facet in enumerate(ordered_facets, start=1)
    }
    flag_normal_hash = 197
    for p0 in positions_by_dimension[0]:
        face0 = set(face_family[p0])
        for p1 in positions_by_dimension[1]:
            face1 = set(face_family[p1])
            if not face0 < face1:
                continue
            for p2 in positions_by_dimension[2]:
                face2 = set(face_family[p2])
                if not face1 < face2:
                    continue
                for p3 in positions_by_dimension[3]:
                    face3 = set(face_family[p3])
                    if not face2 < face3:
                        continue
                    facet_position = facet_positions[face_family[p3]]
                    for value in (
                        p0 + 1,
                        p1 + 1,
                        p2 + 1,
                        p3 + 1,
                        facet_position,
                        *facets[ordered_facets[facet_position - 1]],
                        len(containing_positions(face_family[p0])),
                        len(containing_positions(face_family[p1])),
                        len(containing_positions(face_family[p2])),
                    ):
                        flag_normal_hash = (
                            flag_normal_hash * HASH_BASE + value
                        ) % HASH_MOD
    lines.append(f"FACET_HASH {facet_hash}")
    lines.append(f"TRIPLE_FACE_HASH {triple_face_hash}")
    lines.append(f"NORMAL_HASH {normal_hash}")
    lines.append(f"PAIR_NORMAL_HASH {pair_normal_hash}")
    lines.append(f"INTERSECTION_HASH {intersection_hash}")
    lines.append(f"CARRIER_SIGN_HASH {carrier_sign_hash}")
    lines.append(f"VERTEX_FIGURE_HASH {vertex_figure_hash}")
    lines.append(f"FACET_TRIPLE_HASH {facet_triple_hash}")
    lines.append(f"FACET_QUAD_HASH {facet_quad_hash}")
    lines.append(f"FACE_LATTICE_HASH {face_lattice_hash}")
    lines.append(f"FLAG_HASH {flag_hash}")
    lines.append(f"FACET_CARRIER_HASH {facet_carrier_hash}")
    lines.append(f"FACE_NORMAL_HASH {face_normal_hash}")
    lines.append(f"NORMAL_GRAM_HASH {normal_gram_hash}")
    lines.append(f"FLAG_NORMAL_HASH {flag_normal_hash}")
    return "\n".join(lines) + "\n"


def cases():
    rng = random.Random(0x4D)
    out = []
    for index in range(72):
        vectors = []
        while len(vectors) < 3 + index % 4:
            v = tuple(rng.randrange(2, 80) * (1 if rng.randrange(2) else -1) for _ in range(4))
            if v not in vectors and tuple(-x for x in v) not in vectors:
                vectors.append(v)
        points = [v for v in vectors for v in (v, tuple(-x for x in v))]
        points.extend(tuple(rng.randrange(-8, 9) for _ in range(4)) for _ in range(index % 3))
        rng.shuffle(points)
        if (
            len(points) >= 5
            and len(reference_facet_profile(tuple(points)).splitlines()) >= 3
        ):
            out.append(tuple(points))
    for seed in range(48):
        scale = 130 + seed % 17
        shear = 3 + seed % 9
        points = []
        for bits in itertools.product((-1, 1), repeat=4):
            x0, x1, x2, x3 = bits
            points.append((
                scale * (x0 + 2 * x1) + shear * x2,
                scale * (3 * x1 - x2) + (seed + 5) * x3,
                scale * (x2 + x3) - (2 * seed + 7) * x0,
                scale * (2 * x3 - x0) + (seed % 5) * x1,
            ))
        if seed % 3 == 0:
            points = points[::2] + points[1::2]
        elif seed % 3 == 1:
            points = points[5:] + points[:5]
        out.append(tuple(points))
    for seed in range(12):
        count = 5 + seed % 8
        points = []
        for i in range(count):
            points.append((
                97 * seed + 11 * i,
                (i * i + 13 * seed) % 211 - 105,
                (i * i * i + 7 * seed * i) % 307 - 153,
                4000 - 17 * seed,
            ))
        out.append(tuple(points))
    for seed in range(36):
        count = 10 + seed % 7
        ts = list(range(-8, 8))
        shift = seed % len(ts)
        ts = (ts[shift:] + ts[:shift])[:count]
        points = []
        for t in ts:
            points.append((
                t + seed % 5,
                t * t + (seed % 3) * t - 40,
                t * t * t + 3 * seed - 11 * (seed % 4),
                t * t * t * t - 2 * t * t + 7 * (seed % 6),
            ))
        if seed % 2:
            points = points[3:] + points[:3]
        out.append(tuple(points))
    for seed in range(36):
        rng2 = random.Random(0xFBF700 + seed)
        count = 11 + seed % 6
        points = []
        while len(points) < count:
            point = tuple(rng2.randrange(-9000, 9001) for _ in range(4))
            if point not in points:
                points.append(point)
        out.append(tuple(points))
    return out


def high_coordinate_nonsimplicial_cases():
    out = []
    for seed in range(24):
        scale = 1520 + 29 * (seed % 8)
        shift = (
            3200 - 47 * (seed % 5),
            -3150 + 41 * (seed % 7),
            3050 - 37 * (seed % 6),
            6900 - 43 * (seed % 9),
        )
        permutation = tuple((axis + seed) % 4 for axis in range(4))
        points = []
        for bits in itertools.product((-1, 1), repeat=4):
            u = tuple(bits[index] for index in permutation)
            points.append(
                (
                    shift[0] + scale * (2 * u[0] + u[1]),
                    shift[1] + scale * (u[1] + 2 * u[2]),
                    shift[2] + scale * (u[2] + 2 * u[3]),
                    shift[3] + scale * u[3],
                )
            )
        out.append(tuple(points))
    for seed in range(24):
        scale = 1580 + 31 * (seed % 7)
        center = (
            3150 - 43 * (seed % 6),
            -3100 + 47 * (seed % 5),
            3000 - 53 * (seed % 4),
        )
        base_height = -7900 + 12 * seed
        apex_height = 7900 - 16 * seed
        permutation = tuple((axis + seed) % 3 for axis in range(3))
        points = []
        for bits in itertools.product((-1, 1), repeat=3):
            u = tuple(bits[index] for index in permutation)
            points.append(
                (
                    center[0] + scale * (2 * u[0] + u[1]),
                    center[1] + scale * (u[1] + 2 * u[2]),
                    center[2] + scale * (2 * u[2] - u[0]),
                    base_height,
                )
            )
        points.append((*center, apex_height))
        points.append((*center, (3 * base_height + apex_height) // 4))
        points.append((*center, (base_height + apex_height) // 2))
        out.append(tuple(points))
    return out


ADVERSARIAL_CASES = high_coordinate_nonsimplicial_cases()
BASE_CASES = cases()
CASES = BASE_CASES + ADVERSARIAL_CASES
SCRATCH_ROOT = Path("/tmp/fbf7_geometry_workspace")
SOLVER = SCRATCH_ROOT / "bin" / "hull4_facet_profile"
RUN_UID = 65534
RUN_GID = 65534


def drop_privileges():
    os.setgid(RUN_GID)
    os.setuid(RUN_UID)


def stage_geometry_evaluator():
    if SCRATCH_ROOT.exists():
        shutil.rmtree(SCRATCH_ROOT)
    (SCRATCH_ROOT / "src").mkdir(parents=True)
    shutil.copy2("/app/Makefile", SCRATCH_ROOT / "Makefile")
    shutil.copy2("/app/src/main.cpp", SCRATCH_ROOT / "src" / "main.cpp")
    for path in (
        SCRATCH_ROOT,
        SCRATCH_ROOT / "src",
        SCRATCH_ROOT / "Makefile",
        SCRATCH_ROOT / "src" / "main.cpp",
    ):
        os.chown(path, RUN_UID, RUN_GID)
    os.chmod(SCRATCH_ROOT, 0o755)
    os.chmod(SCRATCH_ROOT / "src", 0o755)
    os.chmod(SCRATCH_ROOT / "Makefile", 0o644)
    os.chmod(SCRATCH_ROOT / "src" / "main.cpp", 0o644)


@pytest.fixture(scope="session", autouse=True)
def prepare_four_dimensional_profile():
    stage_geometry_evaluator()
    subprocess.run(
        ["make", "clean", "all"],
        cwd=SCRATCH_ROOT,
        check=True,
        capture_output=True,
        text=True,
        preexec_fn=drop_privileges,
    )
    assert SOLVER.is_file()


def execute(points):
    points = tuple(points)
    data = str(len(points)) + "\n" + "\n".join(" ".join(map(str, p)) for p in points) + "\n"
    result = subprocess.run(
        [str(SOLVER)],
        input=data,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        cwd="/tmp",
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        preexec_fn=drop_privileges,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == reference_facet_profile(points)


@pytest.mark.parametrize("index", range(len(CASES)))
def test_exact_rank_four_face_case(index):
    """Verify rank-four carrier orientation, facet merging, and boundary membership."""
    execute(CASES[index])


def test_relabeling_metamorphism():
    """Relabeling points changes only the one-based IDs in the canonical signature."""
    points = list(CASES[12])
    points = points[::2] + points[1::2]
    execute(points)


def test_wrong_semantics_are_separated():
    """Interior points and non-simplicial face families defeat common shortcuts."""
    assert len(CASES) >= 60
    assert any(
        "FACET 5" in reference_facet_profile(points) or "FACET 6" in reference_facet_profile(points)
        for points in CASES
    )
    assert "FACET_HASH" in reference_facet_profile(CASES[0])
    assert "TRIPLE_FACE_HASH" in reference_facet_profile(CASES[0])
    assert "NORMAL_HASH" in reference_facet_profile(CASES[0])
    assert "PAIR_NORMAL_HASH" in reference_facet_profile(CASES[0])
    assert "INTERSECTION_HASH" in reference_facet_profile(CASES[0])
    assert "CARRIER_SIGN_HASH" in reference_facet_profile(CASES[0])
    assert "VERTEX_FIGURE_HASH" in reference_facet_profile(CASES[0])
    assert "FACET_TRIPLE_HASH" in reference_facet_profile(CASES[0])
    assert "FACET_QUAD_HASH" in reference_facet_profile(CASES[0])
    assert "FACE_LATTICE_HASH" in reference_facet_profile(CASES[0])
    assert "FLAG_HASH" in reference_facet_profile(CASES[0])
    assert "FACET_CARRIER_HASH" in reference_facet_profile(CASES[0])
    assert "FACE_NORMAL_HASH" in reference_facet_profile(CASES[0])
    assert "NORMAL_GRAM_HASH" in reference_facet_profile(CASES[0])
    assert "FLAG_NORMAL_HASH" in reference_facet_profile(CASES[0])
    assert any(reference_facet_profile(points).startswith("HULL 0\nFACETS 0\n") for points in CASES)
    assert len({reference_facet_profile(points).split("NORMAL_HASH ")[1] for points in CASES[72:96]}) == 24
    assert len({reference_facet_profile(points).split("PAIR_NORMAL_HASH ")[1] for points in CASES[72:96]}) == 24
    assert len({reference_facet_profile(points).split("CARRIER_SIGN_HASH ")[1] for points in BASE_CASES[-36:]}) == 36


@functools.cache
def exposed_facets(points):
    facets = {}
    for ids in itertools.combinations(range(len(points)), 4):
        carrier = primitive_carrier(points, ids)
        if carrier is None:
            continue
        facet = tuple(
            index
            for index, point in enumerate(points)
            if sum(
                coefficient * coordinate
                for coefficient, coordinate in zip(carrier[:4], point)
            )
            + carrier[4]
            == 0
        )
        facets.setdefault(facet, carrier)
    return facets


def first_four_shortcut_normal_hash(points):
    value_hash = 43
    for facet in sorted(exposed_facets(points)):
        shortcut = primitive_carrier(points, facet[:4])
        if shortcut is None:
            shortcut = (0, 0, 0, 0, 0)
        for value in (
            len(facet),
            *(vertex + 1 for vertex in facet),
            *shortcut,
        ):
            value_hash = (
                value_hash * HASH_BASE + value
            ) % HASH_MOD
    return value_hash


def test_adversarial_nonsimplicial_carriers_reject_prefix_shortcut():
    assert len(ADVERSARIAL_CASES) == 48
    assert all(
        max(abs(coordinate) for point in points for coordinate in point) >= 7000
        for points in ADVERSARIAL_CASES
    )
    dependent_prefix_cases = 0
    shortcut_failures = 0
    for points in ADVERSARIAL_CASES:
        facets = exposed_facets(points)
        if any(
            len(facet) > 4
            and not any(hyperplane_coefficients(points, facet[:4]))
            for facet in facets
        ):
            dependent_prefix_cases += 1
        expected = next(
            int(line.split()[1])
            for line in reference_facet_profile(points).splitlines()
            if line.startswith("NORMAL_HASH ")
        )
        shortcut_failures += first_four_shortcut_normal_hash(points) != expected
    assert dependent_prefix_cases >= 40
    assert shortcut_failures >= 40
