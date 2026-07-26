import hashlib
import itertools
import json
import math
import os
import subprocess
from copy import deepcopy
from functools import cache
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
TOOL = APP / "bin" / "boys-localization-sweep"
PUBLIC = APP / "fixtures" / "public.json"
PUBLIC_HASH = "8fbdb99d6ef40545408f5e9e9f8ad7cb4204daac62355341d7049158deadf61e"
RESULT_FIELDS = {
    "id",
    "transform",
    "centroids",
    "objective_trace",
    "accepted_sweeps",
    "sweep_audit",
    "checksum",
}
SWEEP_FIELDS = {
    "sweep",
    "rotations",
    "plan_frontier",
    "total_predicted_gain",
    "total_gain_units",
    "work_used",
    "objective_after",
}
ROTATION_FIELDS = {
    "pair",
    "mode",
    "angle_rad",
    "predicted_gain",
    "gain_units",
    "work_cost",
}
FRONTIER_FIELDS = {
    "sequence",
    "total_gain_units",
    "proposal_count",
    "work_used",
}
CHOICE_FIELDS = {"pair", "mode"}
MODE_RANK = {"direct": 0, "capped": 1, "full": 2}


def generated_dipoles(n, seed):
    dipoles = []
    for coordinate in range(3):
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    value = (
                        0.83 * math.sin((seed + 5 * coordinate + 7 * i) * 0.293)
                        + 0.21 * (coordinate + 1)
                        - 0.065 * i
                    )
                else:
                    value = (
                        0.36
                        * math.cos(
                            (seed + 11 * coordinate + 3 * i + 5 * j) * 0.317
                        )
                        + 0.055 * math.sin((i + j + coordinate + 1) * 0.619)
                    )
                value = round(value, 9)
                matrix[i][j] = value
                matrix[j][i] = value
        dipoles.append(matrix)
    return dipoles


def generated_case(case_id, n, seed, **updates):
    case = {
        "id": case_id,
        "dipoles": generated_dipoles(n, seed),
        "frozen": [False] * n,
        "max_sweeps": 5,
        "max_pairs_per_sweep": min(3, n // 2),
        "work_budget": min(4, 2 * min(3, n // 2)),
        "angle_cap_rad": 0.17,
        "min_gain": 1e-8,
        "gain_quantum": 0.003,
        "convergence_atol": 0.0001,
        "convergence_rtol": 0.0004,
        "frontier_size": 4,
    }
    case.update(updates)
    return case


def clone_matrices(source):
    return [[list(row) for row in matrix] for matrix in source]


def identity(n):
    return [[1.0 if row == column else 0.0 for column in range(n)] for row in range(n)]


def pair_gain(dipoles, i, j, angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    gain = 0.0
    for matrix in dipoles:
        dii = matrix[i][i]
        djj = matrix[j][j]
        dij = matrix[i][j]
        new_ii = (
            cosine * cosine * dii
            + 2 * cosine * sine * dij
            + sine * sine * djj
        )
        new_jj = (
            sine * sine * dii
            - 2 * cosine * sine * dij
            + cosine * cosine * djj
        )
        gain += new_ii * new_ii + new_jj * new_jj - dii * dii - djj * djj
    return gain


def make_proposal(case, dipoles, i, j, mode, angle, work_cost):
    gain = pair_gain(dipoles, i, j, angle)
    units = math.floor(gain / case["gain_quantum"] + 0.5)
    if gain <= case["min_gain"] or units < 1:
        return None
    return {
        "pair": [i, j],
        "mode": mode,
        "angle_rad": angle,
        "predicted_gain": gain,
        "gain_units": units,
        "work_cost": work_cost,
    }


def proposals(case, dipoles):
    result = []
    n = len(case["frozen"])
    for i in range(n):
        if case["frozen"][i]:
            continue
        for j in range(i + 1, n):
            if case["frozen"][j]:
                continue
            a = 0.0
            b = 0.0
            cross = 0.0
            for matrix in dipoles:
                x_value = (matrix[i][i] - matrix[j][j]) / 2
                y_value = matrix[i][j]
                a += x_value * x_value
                b += y_value * y_value
                cross += x_value * y_value
            angle = 0.0
            if a != b or cross != 0:
                angle = 0.25 * math.atan2(2 * cross, a - b)
            if angle >= math.pi / 4:
                angle -= math.pi / 2
            if abs(angle) <= case["angle_cap_rad"]:
                proposal = make_proposal(case, dipoles, i, j, "direct", angle, 1)
                if proposal is not None:
                    result.append(proposal)
            else:
                capped = math.copysign(case["angle_cap_rad"], angle)
                for mode, proposal_angle, cost in (
                    ("capped", capped, 1),
                    ("full", angle, 2),
                ):
                    proposal = make_proposal(
                        case, dipoles, i, j, mode, proposal_angle, cost
                    )
                    if proposal is not None:
                        result.append(proposal)
    return result


def proposal_key(proposal):
    return (
        proposal["pair"][0],
        proposal["pair"][1],
        MODE_RANK[proposal["mode"]],
    )


def valid_plan(case, plan):
    used = set()
    work = 0
    pairs = set()
    for proposal in plan:
        pair = tuple(proposal["pair"])
        if pair in pairs or any(index in used for index in pair):
            return False
        pairs.add(pair)
        used.update(pair)
        work += proposal["work_cost"]
    return work <= case["work_budget"]


def choose_plans(case, available):
    ordered = sorted(available, key=proposal_key)
    by_first_orbital = [[] for _ in case["frozen"]]
    active_mask = 0
    for orbital, frozen in enumerate(case["frozen"]):
        if not frozen:
            active_mask |= 1 << orbital
    for index, proposal in enumerate(ordered):
        by_first_orbital[proposal["pair"][0]].append(index)

    def rank(plan):
        return (
            -sum(ordered[index]["gain_units"] for index in plan),
            -len(plan),
            sum(ordered[index]["work_cost"] for index in plan),
            tuple(proposal_key(ordered[index]) for index in plan),
        )

    def best_distinct(candidates):
        unique = sorted(set(candidates), key=rank)
        return tuple(unique[: case["frontier_size"]])

    @cache
    def solve(mask, pairs_left, work_left):
        if mask == 0 or pairs_left == 0 or work_left == 0:
            return ((),)
        first_bit = mask & -mask
        first = first_bit.bit_length() - 1
        candidates = list(solve(mask ^ first_bit, pairs_left, work_left))
        for proposal_index in by_first_orbital[first]:
            proposal = ordered[proposal_index]
            second = proposal["pair"][1]
            second_bit = 1 << second
            cost = proposal["work_cost"]
            if mask & second_bit == 0 or cost > work_left:
                continue
            suffixes = solve(
                mask ^ first_bit ^ second_bit,
                pairs_left - 1,
                work_left - cost,
            )
            candidates.extend((proposal_index, *suffix) for suffix in suffixes)
        return best_distinct(candidates)

    selected = solve(
        active_mask,
        case["max_pairs_per_sweep"],
        case["work_budget"],
    )
    return [[ordered[index] for index in plan] for plan in selected]


def choose_plan(case, available):
    return choose_plans(case, available)[0]


def frontier_record(plan):
    return {
        "sequence": [
            {"pair": proposal["pair"], "mode": proposal["mode"]}
            for proposal in plan
        ],
        "total_gain_units": sum(item["gain_units"] for item in plan),
        "proposal_count": len(plan),
        "work_used": sum(item["work_cost"] for item in plan),
    }


def apply_rotation(dipoles, transform, proposal):
    i, j = proposal["pair"]
    cosine = math.cos(proposal["angle_rad"])
    sine = math.sin(proposal["angle_rad"])
    cosine_squared = cosine * cosine
    sine_squared = sine * sine
    for coordinate, old in enumerate(dipoles):
        new = [list(row) for row in old]
        dii = old[i][i]
        djj = old[j][j]
        dij = old[i][j]
        new[i][i] = (
            cosine_squared * dii + 2 * cosine * sine * dij + sine_squared * djj
        )
        new[j][j] = (
            sine_squared * dii - 2 * cosine * sine * dij + cosine_squared * djj
        )
        new[i][j] = (cosine_squared - sine_squared) * dij + cosine * sine * (
            djj - dii
        )
        new[j][i] = new[i][j]
        for k in range(len(old)):
            if k == i or k == j:
                continue
            new_ik = cosine * old[i][k] + sine * old[j][k]
            new_jk = -sine * old[i][k] + cosine * old[j][k]
            new[i][k] = new_ik
            new[k][i] = new_ik
            new[j][k] = new_jk
            new[k][j] = new_jk
        dipoles[coordinate] = new
    for row in range(len(transform)):
        old_i = transform[row][i]
        old_j = transform[row][j]
        transform[row][i] = cosine * old_i + sine * old_j
        transform[row][j] = -sine * old_i + cosine * old_j


def objective(dipoles):
    return math.fsum(
        matrix[index][index] * matrix[index][index]
        for matrix in dipoles
        for index in range(len(matrix))
    )


def expected_case(case):
    dipoles = clone_matrices(case["dipoles"])
    n = len(case["frozen"])
    transform = identity(n)
    trace = [objective(dipoles)]
    accepted = []
    audit = []
    for sweep in range(1, case["max_sweeps"] + 1):
        ranked_plans = choose_plans(case, proposals(case, dipoles))
        plan = ranked_plans[0]
        total_gain = math.fsum(item["predicted_gain"] for item in plan)
        for proposal in plan:
            apply_rotation(dipoles, transform, proposal)
        objective_after = objective(dipoles)
        trace.append(objective_after)
        if total_gain <= case["convergence_atol"] + case["convergence_rtol"] * abs(
            objective_after
        ):
            accepted.append(sweep)
        audit.append(
            {
                "sweep": sweep,
                "rotations": plan,
                "plan_frontier": [
                    frontier_record(frontier_plan) for frontier_plan in ranked_plans
                ],
                "total_predicted_gain": total_gain,
                "total_gain_units": sum(item["gain_units"] for item in plan),
                "work_used": sum(item["work_cost"] for item in plan),
                "objective_after": objective_after,
            }
        )
    centroids = [
        [dipoles[coordinate][index][index] for coordinate in range(3)]
        for index in range(n)
    ]
    checksum = math.fsum(
        (index + 1) * (coordinate + 1) * centroids[index][coordinate]
        for index in range(n)
        for coordinate in range(3)
    ) + math.fsum(
        ((row + 1) * (column + 1) / n) * transform[row][column]
        for row in range(n)
        for column in range(n)
    )
    return {
        "id": case["id"],
        "transform": transform,
        "centroids": centroids,
        "objective_trace": trace,
        "accepted_sweeps": accepted,
        "sweep_audit": audit,
        "checksum": checksum,
    }


def assert_close(actual, expected):
    assert type(actual) is int or type(actual) is float
    assert math.isfinite(actual)
    assert actual == pytest.approx(expected, rel=2e-9, abs=2e-10)


def compare_matrix(actual, expected):
    assert isinstance(actual, list)
    assert len(actual) == len(expected)
    for actual_row, expected_row in zip(actual, expected, strict=True):
        assert isinstance(actual_row, list)
        assert len(actual_row) == len(expected_row)
        for actual_value, expected_value in zip(
            actual_row, expected_row, strict=True
        ):
            assert_close(actual_value, expected_value)


def compare_result(actual, expected, case):
    assert set(actual) == RESULT_FIELDS
    assert actual["id"] == expected["id"]
    compare_matrix(actual["transform"], expected["transform"])
    compare_matrix(actual["centroids"], expected["centroids"])
    assert len(actual["objective_trace"]) == len(expected["objective_trace"])
    for got, wanted in zip(
        actual["objective_trace"], expected["objective_trace"], strict=True
    ):
        assert_close(got, wanted)
    assert actual["accepted_sweeps"] == expected["accepted_sweeps"]
    assert len(actual["sweep_audit"]) == len(expected["sweep_audit"])
    for got_sweep, wanted_sweep in zip(
        actual["sweep_audit"], expected["sweep_audit"], strict=True
    ):
        assert set(got_sweep) == SWEEP_FIELDS
        for field in ("sweep", "total_gain_units", "work_used"):
            assert got_sweep[field] == wanted_sweep[field]
        for field in ("total_predicted_gain", "objective_after"):
            assert_close(got_sweep[field], wanted_sweep[field])
        assert len(got_sweep["rotations"]) == len(wanted_sweep["rotations"])
        for got_rotation, wanted_rotation in zip(
            got_sweep["rotations"], wanted_sweep["rotations"], strict=True
        ):
            assert set(got_rotation) == ROTATION_FIELDS
            for field in ("pair", "mode", "gain_units", "work_cost"):
                assert got_rotation[field] == wanted_rotation[field]
            assert_close(got_rotation["angle_rad"], wanted_rotation["angle_rad"])
            assert_close(
                got_rotation["predicted_gain"], wanted_rotation["predicted_gain"]
            )
        assert len(got_sweep["plan_frontier"]) == len(
            wanted_sweep["plan_frontier"]
        )
        for got_plan, wanted_plan in zip(
            got_sweep["plan_frontier"],
            wanted_sweep["plan_frontier"],
            strict=True,
        ):
            assert set(got_plan) == FRONTIER_FIELDS
            for field in ("total_gain_units", "proposal_count", "work_used"):
                assert got_plan[field] == wanted_plan[field]
            assert len(got_plan["sequence"]) == len(wanted_plan["sequence"])
            for got_choice, wanted_choice in zip(
                got_plan["sequence"], wanted_plan["sequence"], strict=True
            ):
                assert set(got_choice) == CHOICE_FIELDS
                assert got_choice == wanted_choice
    assert_close(actual["checksum"], expected["checksum"])
    assert_numerical_invariants(actual, case)


def transformed_entry(transform, matrix, row, column):
    n = len(transform)
    return math.fsum(
        transform[left][row] * matrix[left][right] * transform[right][column]
        for left in range(n)
        for right in range(n)
    )


def assert_numerical_invariants(result, case):
    transform = result["transform"]
    n = len(transform)
    for left in range(n):
        for right in range(n):
            dot = math.fsum(
                transform[row][left] * transform[row][right] for row in range(n)
            )
            assert dot == pytest.approx(
                1.0 if left == right else 0.0, rel=2e-9, abs=2e-10
            )
    reconstructed_objective = 0.0
    for index in range(n):
        for coordinate, matrix in enumerate(case["dipoles"]):
            diagonal = transformed_entry(transform, matrix, index, index)
            assert result["centroids"][index][coordinate] == pytest.approx(
                diagonal, rel=2e-9, abs=2e-10
            )
            reconstructed_objective += diagonal * diagonal
    assert result["objective_trace"][-1] == pytest.approx(
        reconstructed_objective, rel=2e-9, abs=2e-10
    )
    for before, after in itertools.pairwise(result["objective_trace"]):
        assert after >= before - (2e-10 + 2e-9 * abs(before))
    for sweep in result["sweep_audit"]:
        used = set()
        work = 0
        assert len(sweep["rotations"]) <= case["max_pairs_per_sweep"]
        for rotation in sweep["rotations"]:
            assert not used.intersection(rotation["pair"])
            used.update(rotation["pair"])
            work += rotation["work_cost"]
        assert work == sweep["work_used"]
        assert work <= case["work_budget"]
        frontier = sweep["plan_frontier"]
        assert 1 <= len(frontier) <= case["frontier_size"]
        sequences = []
        ranks = []
        for plan in frontier:
            sequence = tuple(
                (
                    choice["pair"][0],
                    choice["pair"][1],
                    MODE_RANK[choice["mode"]],
                )
                for choice in plan["sequence"]
            )
            assert sequence == tuple(sorted(sequence))
            assert plan["proposal_count"] == len(sequence)
            sequences.append(sequence)
            ranks.append(
                (
                    -plan["total_gain_units"],
                    -plan["proposal_count"],
                    plan["work_used"],
                    sequence,
                )
            )
        assert len(set(sequences)) == len(sequences)
        assert ranks == sorted(ranks)
        assert [
            (rotation["pair"][0], rotation["pair"][1], MODE_RANK[rotation["mode"]])
            for rotation in sweep["rotations"]
        ] == list(sequences[0])
        assert frontier[0]["total_gain_units"] == sweep["total_gain_units"]
        assert frontier[0]["work_used"] == sweep["work_used"]


def compare_output(actual, cases):
    assert set(actual) == {"results"}
    assert isinstance(actual["results"], list)
    assert len(actual["results"]) == len(cases)
    for got, case in zip(actual["results"], cases, strict=True):
        compare_result(got, expected_case(case), case)


def run_payload(payload, label):
    directory = APP / "out" / label
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "input.json"
    output_path = directory / "result.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    before = hashlib.sha256(input_path.read_bytes()).hexdigest()
    environment = os.environ | {"PATH": "/path-intentionally-empty"}
    proc = subprocess.run(
        [str(TOOL), str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
        env=environment,
    )
    assert proc.returncode == 0, proc.stderr
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == before
    return json.loads(output_path.read_text(encoding="utf-8"))


def payload_for(*cases):
    return {"task": "boys-localization-sweep", "cases": list(cases)}


def tie_case():
    dipoles = []
    for coordinate in range(3):
        matrix = [[0.0] * 4 for _ in range(4)]
        if coordinate == 0:
            for offset in (0, 2):
                matrix[offset][offset] = 1.0
                matrix[offset + 1][offset + 1] = -1.0
                matrix[offset][offset + 1] = 0.2
                matrix[offset + 1][offset] = 0.2
        dipoles.append(matrix)
    return {
        "id": "complete-plan-tie",
        "dipoles": dipoles,
        "frozen": [False] * 4,
        "max_sweeps": 1,
        "max_pairs_per_sweep": 1,
        "work_budget": 1,
        "angle_cap_rad": 0.3,
        "min_gain": 0.0,
        "gain_quantum": 0.001,
        "convergence_atol": 0.0,
        "convergence_rtol": 0.0,
        "frontier_size": 4,
    }


def boundary_case():
    dipoles = [[[0.0] * 4 for _ in range(4)] for _ in range(3)]
    dipoles[0][0][1] = 1.0
    dipoles[0][1][0] = 1.0
    dipoles[1][2][2] = 0.4
    dipoles[1][3][3] = -0.4
    return {
        "id": "half-open-angle-boundary",
        "dipoles": dipoles,
        "frozen": [False, False, True, True],
        "max_sweeps": 3,
        "max_pairs_per_sweep": 2,
        "work_budget": 2,
        "angle_cap_rad": 0.2,
        "min_gain": 0.0,
        "gain_quantum": 0.001,
        "convergence_atol": 0.0,
        "convergence_rtol": 0.0,
        "frontier_size": 4,
    }


RUNTIME_FAMILY_IDS = [f"family-{index:02d}" for index in range(8)]


def runtime_family_case(case_id):
    index = int(case_id.rsplit("-", 1)[1])
    n = 4 + index % 6
    max_pairs = min(3, n // 2)
    frozen = [False] * n
    if index % 3 == 1:
        frozen[(index + 1) % n] = True
        frozen[(index + 3) % n] = True
    elif index % 4 == 2:
        frozen = [orbital % 4 == 0 for orbital in range(n)]
    if sum(not item for item in frozen) < 2:
        frozen = [False] * n
    return generated_case(
        f"runtime-{index:02d}",
        n,
        71 + 19 * index,
        frozen=frozen,
        max_sweeps=3 + index % 4,
        max_pairs_per_sweep=max_pairs,
        work_budget=min(2 * max_pairs, max_pairs + (index % (max_pairs + 1))),
        angle_cap_rad=0.08 + 0.015 * ((2 * index) % 7),
        min_gain=0.0 if index % 2 == 0 else 0.001 * (1 + index % 3),
        gain_quantum=0.002 + 0.004 * (index % 5),
        convergence_atol=1e-5 * (1 + index % 4),
        convergence_rtol=0.0002 + 0.0001 * (index % 4),
    )


def special_case(kind):
    if kind == "greedy-pair-trap":
        return generated_case(
            "greedy-pair-trap",
            8,
            13,
            max_sweeps=4,
            max_pairs_per_sweep=3,
            work_budget=4,
            angle_cap_rad=0.14,
            gain_quantum=0.004,
        )
    if kind == "action-family-competition":
        return generated_case(
            "capped-full-work-competition",
            8,
            1,
            max_sweeps=5,
            max_pairs_per_sweep=3,
            work_budget=3,
            angle_cap_rad=0.08,
            gain_quantum=0.002,
        )
    if kind == "batch-large":
        return generated_case("batch-large", 9, 163, max_sweeps=4, work_budget=5)
    if kind == "batch-all-frozen":
        return generated_case(
            "batch-all-frozen",
            5,
            179,
            frozen=[True] * 5,
            max_sweeps=3,
            max_pairs_per_sweep=2,
            work_budget=2,
        )
    if kind == "stress":
        return generated_case(
            "stress-twelve-orbitals",
            12,
            211,
            frozen=[
                False,
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,
            ],
            max_sweeps=8,
            max_pairs_per_sweep=3,
            work_budget=5,
            angle_cap_rad=0.095,
            min_gain=1e-7,
            gain_quantum=0.0015,
            convergence_atol=0.00001,
            convergence_rtol=0.0001,
        )
    if kind == "dense-planner":
        return generated_case(
            "dense-twenty-orbital-planner",
            20,
            307,
            max_sweeps=2,
            max_pairs_per_sweep=10,
            work_budget=20,
            angle_cap_rad=0.045,
            min_gain=0.0,
            gain_quantum=0.001,
            convergence_atol=0.00001,
            convergence_rtol=0.0001,
        )
    if kind == "invalid-base":
        return generated_case("invalid", 5, 223)
    if kind == "good-first":
        return generated_case("good-first", 6, 227)
    if kind == "bad-second":
        return generated_case("bad-second", 6, 229)
    raise ValueError(f"unknown special case kind: {kind}")


def greedy_plan(case, available):
    ordered = sorted(
        available,
        key=lambda item: (-item["gain_units"], proposal_key(item)),
    )
    selected = []
    for proposal in ordered:
        trial = [*selected, proposal]
        if len(trial) <= case["max_pairs_per_sweep"] and valid_plan(case, trial):
            selected = trial
    return selected


def plan_units(plan):
    return sum(item["gain_units"] for item in plan)


def proposals_without_half_open(case, dipoles):
    result = []
    n = len(case["frozen"])
    for i in range(n):
        if case["frozen"][i]:
            continue
        for j in range(i + 1, n):
            if case["frozen"][j]:
                continue
            a = 0.0
            b = 0.0
            cross = 0.0
            for matrix in dipoles:
                x_value = (matrix[i][i] - matrix[j][j]) / 2
                y_value = matrix[i][j]
                a += x_value * x_value
                b += y_value * y_value
                cross += x_value * y_value
            angle = 0.0
            if a != b or cross != 0:
                angle = 0.25 * math.atan2(2 * cross, a - b)
            if abs(angle) <= case["angle_cap_rad"]:
                proposal = make_proposal(case, dipoles, i, j, "direct", angle, 1)
                if proposal is not None:
                    result.append(proposal)
            else:
                capped = math.copysign(case["angle_cap_rad"], angle)
                for mode, proposal_angle, cost in (
                    ("capped", capped, 1),
                    ("full", angle, 2),
                ):
                    proposal = make_proposal(
                        case, dipoles, i, j, mode, proposal_angle, cost
                    )
                    if proposal is not None:
                        result.append(proposal)
    return result


def expected_case_with_planner(case, proposal_fn, planner_fn):
    dipoles = clone_matrices(case["dipoles"])
    n = len(case["frozen"])
    transform = identity(n)
    trace = [objective(dipoles)]
    accepted = []
    audit = []
    for sweep in range(1, case["max_sweeps"] + 1):
        available = proposal_fn(case, dipoles)
        plan = planner_fn(case, available)
        total_gain = math.fsum(item["predicted_gain"] for item in plan)
        for proposal in plan:
            apply_rotation(dipoles, transform, proposal)
        objective_after = objective(dipoles)
        trace.append(objective_after)
        if total_gain <= case["convergence_atol"] + case["convergence_rtol"] * abs(
            objective_after
        ):
            accepted.append(sweep)
        audit.append(
            {
                "sweep": sweep,
                "rotations": plan,
                "plan_frontier": [frontier_record(plan)],
                "total_predicted_gain": total_gain,
                "total_gain_units": sum(item["gain_units"] for item in plan),
                "work_used": sum(item["work_cost"] for item in plan),
                "objective_after": objective_after,
            }
        )
    centroids = [
        [dipoles[coordinate][index][index] for coordinate in range(3)]
        for index in range(n)
    ]
    checksum = math.fsum(
        (index + 1) * (coordinate + 1) * centroids[index][coordinate]
        for index in range(n)
        for coordinate in range(3)
    ) + math.fsum(
        ((row + 1) * (column + 1) / n) * transform[row][column]
        for row in range(n)
        for column in range(n)
    )
    return {
        "id": case["id"],
        "transform": transform,
        "centroids": centroids,
        "objective_trace": trace,
        "accepted_sweeps": accepted,
        "sweep_audit": audit,
        "checksum": checksum,
    }


def greedy_expected_case(case):
    return expected_case_with_planner(case, proposals, greedy_plan)


def no_half_open_expected_case(case):
    return expected_case_with_planner(case, proposals_without_half_open, choose_plan)


def test_launch_artifact_and_public_input_integrity():
    """Verify the submitted artifact is a native executable and the public fixture is unchanged."""
    assert TOOL.is_file()
    assert os.access(TOOL, os.X_OK)
    assert TOOL.read_bytes()[:4] == b"\x7fELF"
    assert hashlib.sha256(PUBLIC.read_bytes()).hexdigest() == PUBLIC_HASH


def test_public_correctness_and_clean_rerun():
    """Check the public fixture result is correct and deterministic across repeated runs."""
    payload = json.loads(PUBLIC.read_text(encoding="utf-8"))
    output_path = APP / "out" / "public_result.json"
    output_path.unlink(missing_ok=True)
    first_bytes = None
    for _ in range(2):
        proc = subprocess.run(
            [str(TOOL), str(PUBLIC), str(output_path)],
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        compare_output(json.loads(output_path.read_text(encoding="utf-8")), payload["cases"])
        if first_bytes is None:
            first_bytes = output_path.read_bytes()
        else:
            assert output_path.read_bytes() == first_bytes


@pytest.mark.parametrize(
    "case_id", RUNTIME_FAMILY_IDS, ids=[f"runtime-{case_id}" for case_id in RUNTIME_FAMILY_IDS]
)
def test_runtime_compatibility_families(case_id):
    """Exercise deterministic runtime-generated compatible cases across sizes and frozen sets."""
    case = runtime_family_case(case_id)
    actual = run_payload(payload_for(case), f"normal-{case['id']}")
    compare_output(actual, [case])


def test_interaction_greedy_pair_trap():
    """Ensure complete-plan optimization beats locally greedy pair selection."""
    case = special_case("greedy-pair-trap")
    available = proposals(case, clone_matrices(case["dipoles"]))
    optimal = choose_plan(case, available)
    greedy = greedy_plan(case, available)
    assert plan_units(optimal) > plan_units(greedy)
    actual = run_payload(payload_for(case), "interaction-greedy-trap")
    compare_output(actual, [case])


def test_action_families_compete_for_work_budget():
    """Check capped and full proposals compete correctly under the sweep work budget."""
    case = special_case("action-family-competition")
    available = proposals(case, clone_matrices(case["dipoles"]))
    assert {proposal["mode"] for proposal in available} >= {"capped", "full"}
    plan = choose_plan(case, available)
    assert sum(item["work_cost"] for item in plan) == case["work_budget"]
    assert len(plan) >= 2
    actual = run_payload(payload_for(case), "interaction-action-families")
    compare_output(actual, [case])


def test_complete_plan_tie_break_changes_winner():
    """Verify canonical complete-plan tie-breaking selects the lexicographically first plan."""
    case = tie_case()
    available = proposals(case, clone_matrices(case["dipoles"]))
    equal_best = [
        proposal
        for proposal in available
        if proposal["gain_units"] == max(item["gain_units"] for item in available)
    ]
    assert [proposal["pair"] for proposal in equal_best] == [[0, 1], [2, 3]]
    assert choose_plan(case, available)[0]["pair"] == [0, 1]
    frontier = choose_plans(case, available)
    assert [plan[0]["pair"] if plan else None for plan in frontier] == [
        [0, 1],
        [2, 3],
        None,
    ]
    actual = run_payload(payload_for(case), "tie-complete-plan")
    compare_output(actual, [case])


def test_edge_angle_canonicalization_and_empty_later_sweeps():
    """Cover the pi/4 half-open angle boundary and required empty later sweep records."""
    case = boundary_case()
    expected = expected_case(case)
    first = expected["sweep_audit"][0]["rotations"][0]
    assert first["mode"] == "full"
    assert first["angle_rad"] == pytest.approx(-math.pi / 4, abs=1e-15)
    assert expected["sweep_audit"][-1]["rotations"] == []
    assert expected["accepted_sweeps"][-1] == case["max_sweeps"]
    actual = run_payload(payload_for(case), "edge-angle-boundary")
    compare_output(actual, [case])


def test_batch_order_and_generated_generalization():
    """Confirm batches preserve input order and solve mixed generated cases."""
    cases = [
        special_case("batch-large"),
        tie_case() | {"id": "batch-tie"},
        special_case("batch-all-frozen"),
    ]
    actual = run_payload(payload_for(*cases), "generalization-batch")
    compare_output(actual, cases)
    assert [result["id"] for result in actual["results"]] == [
        case["id"] for case in cases
    ]


def test_adversarial_stress_case():
    """Run a larger adversarial case that requires multiple proposal modes."""
    case = special_case("stress")
    actual = run_payload(payload_for(case), "stress")
    compare_output(actual, [case])
    modes = {
        rotation["mode"]
        for sweep in actual["results"][0]["sweep_audit"]
        for rotation in sweep["rotations"]
    }
    assert len(modes) >= 2


def test_dense_exact_matching_planner_scales_to_full_domain():
    """Require exact K-best planning where proposal-subset enumeration explodes."""
    case = special_case("dense-planner")
    available = proposals(case, clone_matrices(case["dipoles"]))
    assert len(available) >= 300
    ranked = choose_plans(case, available)
    plan = ranked[0]
    assert len(plan) == case["max_pairs_per_sweep"]
    assert len(ranked) == case["frontier_size"]
    assert len(
        {
            tuple(proposal_key(proposal) for proposal in candidate)
            for candidate in ranked
        }
    ) == case["frontier_size"]
    assert {proposal["mode"] for proposal in available} >= {"capped", "full"}
    actual = run_payload(payload_for(case), "dense-exact-planner")
    compare_output(actual, [case])


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-top-field",
        "missing-case-field",
        "unknown-case-field",
        "duplicate-id",
        "empty-cases",
        "wrong-dipole-count",
        "ragged-matrix",
        "asymmetric-matrix",
        "wrong-frozen-length",
        "numeric-string",
        "null-array",
        "bad-pair-limit",
        "bad-work-budget",
        "bad-angle-cap",
        "bad-gain-quantum",
        "bad-frontier-size",
        "noninteger-frontier-size",
        "too-many-orbitals",
    ],
)
def test_schema_failures_do_not_create_output(mutation):
    """Reject malformed inputs without creating a successful output file."""
    case = special_case("invalid-base")
    payload = payload_for(case)
    if mutation == "unknown-top-field":
        payload["extra"] = True
    elif mutation == "missing-case-field":
        del case["min_gain"]
    elif mutation == "unknown-case-field":
        case["extra"] = 1
    elif mutation == "duplicate-id":
        payload["cases"].append(deepcopy(case))
    elif mutation == "empty-cases":
        payload["cases"] = []
    elif mutation == "wrong-dipole-count":
        case["dipoles"].pop()
    elif mutation == "ragged-matrix":
        case["dipoles"][0][0].pop()
    elif mutation == "asymmetric-matrix":
        case["dipoles"][0][0][1] += 0.1
    elif mutation == "wrong-frozen-length":
        case["frozen"].pop()
    elif mutation == "numeric-string":
        case["gain_quantum"] = "0.003"
    elif mutation == "null-array":
        case["frozen"] = None
    elif mutation == "bad-pair-limit":
        case["max_pairs_per_sweep"] = 3
    elif mutation == "bad-work-budget":
        case["work_budget"] = 7
    elif mutation == "bad-angle-cap":
        case["angle_cap_rad"] = math.pi / 2
    elif mutation == "bad-gain-quantum":
        case["gain_quantum"] = 1e-9
    elif mutation == "bad-frontier-size":
        case["frontier_size"] = 6
    elif mutation == "noninteger-frontier-size":
        case["frontier_size"] = 3.5
    elif mutation == "too-many-orbitals":
        oversized = generated_case("oversized", 21, 401)
        case["dipoles"] = oversized["dipoles"]
        case["frozen"] = oversized["frozen"]
        case["max_pairs_per_sweep"] = oversized["max_pairs_per_sweep"]
        case["work_budget"] = oversized["work_budget"]
    directory = APP / "out" / f"invalid-{mutation}"
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "input.json"
    output_path = directory / "result.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    output_path.unlink(missing_ok=True)
    proc = subprocess.run(
        [str(TOOL), str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode != 0
    assert not output_path.exists()


@pytest.mark.parametrize("scope", ["top-level", "nested-case"])
def test_duplicate_json_member_name_is_rejected(scope):
    """Reject duplicate names even when keeping either value would otherwise be valid."""
    directory = APP / "out" / "duplicate-json-name"
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "input.json"
    output_path = directory / f"result-{scope}.json"
    case_text = json.dumps(special_case("invalid-base"), separators=(",", ":"))
    if scope == "top-level":
        raw = (
            '{"task":"boys-localization-sweep",'
            '"task":"boys-localization-sweep","cases":['
            + case_text
            + "]}"
        )
    else:
        raw = (
            '{"task":"boys-localization-sweep","cases":['
            + case_text[:-1]
            + ',"id":"still-valid-but-duplicate"}]}'
        )
    input_path.write_text(raw, encoding="utf-8")
    output_path.unlink(missing_ok=True)
    proc = subprocess.run(
        [str(TOOL), str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode != 0
    assert not output_path.exists()


def test_invalid_later_case_preserves_existing_output():
    """Preserve an existing output when any later case in the batch is invalid."""
    good = special_case("good-first")
    bad = special_case("bad-second")
    bad["dipoles"][1][0].pop()
    directory = APP / "out" / "atomic-batch"
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "input.json"
    output_path = directory / "result.json"
    input_path.write_text(json.dumps(payload_for(good, bad)), encoding="utf-8")
    sentinel = b"preserve successful output\n"
    output_path.write_bytes(sentinel)
    proc = subprocess.run(
        [str(TOOL), str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode != 0
    assert output_path.read_bytes() == sentinel


def test_exact_cli_and_input_output_alias_rejection():
    """Require exactly two CLI arguments and reject direct, hard-link, and symlink aliases."""
    for arguments in ([], [str(PUBLIC)], [str(PUBLIC), "a", "b"]):
        proc = subprocess.run(
            [str(TOOL), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert proc.returncode != 0
    alias_copy = APP / "out" / "alias-input.json"
    alias_copy.write_bytes(PUBLIC.read_bytes())
    before = alias_copy.read_bytes()
    proc = subprocess.run(
        [str(TOOL), str(alias_copy), str(alias_copy)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode != 0
    assert alias_copy.read_bytes() == before
    hardlink = APP / "out" / "alias-hardlink.json"
    symlink = APP / "out" / "alias-symlink.json"
    hardlink.unlink(missing_ok=True)
    symlink.unlink(missing_ok=True)
    os.link(alias_copy, hardlink)
    symlink.symlink_to(alias_copy)
    for output_alias in (hardlink, symlink):
        proc = subprocess.run(
            [str(TOOL), str(alias_copy), str(output_alias)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert proc.returncode != 0
        assert alias_copy.read_bytes() == before


def test_oracle_defeats_documented_shallow_strategies():
    """Check that runtime cases still distinguish the intended algorithm from common shortcuts."""
    cases = [
        boundary_case(),
        special_case("greedy-pair-trap"),
        special_case("action-family-competition"),
        runtime_family_case("family-03"),
        runtime_family_case("family-06"),
    ]
    bads = [greedy_expected_case, no_half_open_expected_case]
    for bad in bads:
        assert any(
            bad(case)["sweep_audit"][0]["rotations"]
            != expected_case(case)["sweep_audit"][0]["rotations"]
            for case in cases
        ), bad.__name__
