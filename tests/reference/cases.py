from __future__ import annotations

import random


def _pick_targets(rng: random.Random, nodes: int, caller: int, min_size: int) -> list[int]:
    order = list(range(nodes))
    rng.shuffle(order)
    if caller in order:
        order.remove(caller)
    order.insert(0, caller)
    k = rng.randrange(min_size, nodes + 1)
    return sorted(set(order[:k]))


def _append_recover_window(
    events: list[dict],
    clock: int,
    caller: int,
    node_id: str,
    targets: list[int],
    token: int,
    rng: random.Random,
) -> None:
    crash_node = rng.randrange(max(1, len(targets)))
    crashed = targets[crash_node]
    events.append({"time": clock, "type": "crash", "node": crashed})
    clock += 1
    events.append({"time": clock, "type": "tick", "delta": 1})
    events.append({"time": clock, "type": "recover", "node": crashed})
    events.append({"time": clock + 1, "type": "tick", "delta": 1})
    events.append(
        {
            "time": clock + 1,
            "type": "write",
            "node": caller,
            "token": token,
            "write_id": node_id,
            "targets": targets,
            "value": rng.randrange(1000),
        }
    )


def _build_case(case_id: int, seed: int, nodes: int, ticks: int, hidden: bool) -> dict:
    rng = random.Random(seed)
    events: list[dict] = []
    clock = 0

    caller = rng.randrange(nodes)
    peer = (caller + 1) % nodes

    first_ttl = rng.randrange(1, 6)
    if hidden and rng.random() < 0.6:
        first_ttl = 1

    recipients = _pick_targets(rng, nodes, caller, nodes // 2 + 1)
    events.append(
        {
            "time": clock,
            "type": "request_lease",
            "node": caller,
            "term": rng.randrange(1, 4),
            "ttl": first_ttl,
            "targets": recipients,
            "write_id": "",
        }
    )

    token = 1
    dup_targets = recipients
    if rng.random() < 0.7 and len(dup_targets) > 1:
        dup_targets = dup_targets[:-1]

    events.append(
        {
            "time": clock,
            "type": "write",
            "node": caller,
            "token": token,
            "write_id": f"{case_id:04d}-w0",
            "targets": dup_targets,
            "value": rng.randrange(1000),
        }
    )

    if hidden and rng.random() < 0.45:
        events.append({"time": clock + first_ttl, "type": "tick", "delta": 1})
        events.append(
            {
                "time": clock + first_ttl + 1,
                "type": "write",
                "node": caller,
                "token": token,
                "write_id": f"{case_id:04d}-w0",
                "targets": dup_targets,
                "value": rng.randrange(1000),
            }
        )

    if hidden and rng.random() < 0.6:
        _append_recover_window(
            events,
            clock,
            caller,
            f"{case_id:04d}-w1",
            dup_targets,
            token,
            rng,
        )

    clock = max(e["time"] for e in events)

    if hidden:
        rival_targets = _pick_targets(rng, nodes, peer, nodes // 2)
        events.append(
            {
                "time": clock + 2,
                "type": "request_lease",
                "node": peer,
                "term": rng.randrange(1, 4),
                "ttl": rng.randrange(2, 7),
                "targets": rival_targets,
                "write_id": "",
            }
        )
        events.append(
            {
                "time": clock + 3,
                "type": "write",
                "node": peer,
                "token": 2,
                "write_id": f"{case_id:04d}-w2",
                "targets": rival_targets,
                "value": rng.randrange(1000),
            }
        )
        if rng.random() < 0.5:
            events.append(
                {
                    "time": clock + 4,
                    "type": "write",
                    "node": peer,
                    "token": 2,
                    "write_id": f"{case_id:04d}-w2",
                    "targets": rival_targets,
                    "value": rng.randrange(1000),
                }
            )

    return {
        "case_id": f"case-{case_id:04d}",
        "nodes": nodes,
        "seed": seed,
        "events": events,
        "public": not hidden,
    }


def _edge_cases(start: int) -> list[dict]:
    return [
        {
            "case_id": f"case-{start:04d}",
            "nodes": 5,
            "seed": 9000,
            "events": [
                {"time": 0, "type": "request_lease", "node": 0, "term": 1, "ttl": 5, "targets": [0, 0, 1, 2, 8, -1], "write_id": ""},
                {"time": 1, "type": "write", "node": 0, "token": 1, "write_id": "edge-denied-token", "targets": [0, 1, 1, 8], "value": 7},
                {"time": 2, "type": "write", "node": 0, "token": 99, "write_id": "edge-stale-token", "targets": [0, 1, 2, 3], "value": 8},
                {"time": 2, "type": "mystery_row", "token": 123, "write_id": "unknown-witness"},
                {"time": 3, "type": "write", "node": 0, "token": 1, "write_id": "edge-commit", "targets": [], "value": 9},
            ],
            "public": False,
        },
        {
            "case_id": f"case-{start + 1:04d}",
            "nodes": 5,
            "seed": 9001,
            "events": [
                {"time": 0, "type": "request_lease", "node": 2, "term": 4, "ttl": 4, "targets": [2, 3, 4], "write_id": ""},
                {"time": 1, "type": "crash", "node": 3},
                {"time": 2, "type": "recover", "node": 3},
                {"time": 2, "type": "write", "node": 2, "token": 1, "write_id": "recovered-commit", "targets": [2, 3, 4], "value": 10},
                {"time": 5, "type": "tick", "delta": 1},
                {"time": 6, "type": "write", "node": 2, "token": 1, "write_id": "expired-denial", "targets": [2, 3, 4], "value": 11},
            ],
            "public": False,
        },
    ]


def build_cases():
    cases = []
    nodes = 5
    public_seeds = list(range(1000, 1014))
    hidden_seeds = list(range(2000, 2030))
    for idx, seed in enumerate(public_seeds):
        cases.append(_build_case(idx, seed, nodes, 0, hidden=False))
    for idx, seed in enumerate(hidden_seeds, start=len(public_seeds)):
        cases.append(_build_case(idx, seed, nodes, 0, hidden=True))
    cases.extend(_edge_cases(len(cases)))
    return cases
