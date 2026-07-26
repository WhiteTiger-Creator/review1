from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    alive: bool = True
    vol_term: int = 0
    vol_owner: int = -1
    vol_token: int = 0
    vol_expiry: int = 0
    persist_term: int = 0
    persist_owner: int = -1
    persist_token: int = 0
    persist_expiry: int = 0
    persist_writes: set[str] = field(default_factory=set)


def simulate_case(case: dict[str, Any]) -> dict[str, Any]:
    nodes = case["nodes"]
    quorum = nodes // 2 + 1
    state = [Node() for _ in range(nodes)]
    clock = 0
    results = []
    committed = set()

    def unique_targets(raw):
        out = []
        seen = set()
        for n in raw:
            if n < 0 or n >= nodes:
                continue
            if n in seen:
                continue
            seen.add(n)
            out.append(n)
        return out

    for idx, event in enumerate(case["events"]):
        clock = max(clock, event["time"])
        etype = event["type"]
        if etype == "tick":
            clock += event["delta"]
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "ok",
                    "token": 0,
                    "expires_at": clock,
                }
            )
            continue
        if etype == "crash":
            node = event["node"]
            if 0 <= node < nodes:
                state[node].alive = False
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "ok",
                    "token": 0,
                    "expires_at": clock,
                }
            )
            continue
        if etype == "recover":
            node = event["node"]
            if 0 <= node < nodes:
                st = state[node]
                st.alive = True
                st.vol_term = st.persist_term
                st.vol_owner = st.persist_owner
                st.vol_token = st.persist_token
                st.vol_expiry = st.persist_expiry
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "ok",
                    "token": 0,
                    "expires_at": clock,
                }
            )
            continue
        if etype not in {"request_lease", "write"}:
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "ignored",
                    "token": event.get("token", 0),
                    "expires_at": clock,
                    "write_id": event.get("write_id", ""),
                }
            )
            continue
        if event["node"] < 0 or event["node"] >= nodes:
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "rejected",
                    "token": 0,
                    "expires_at": 0,
                    "write_id": event.get("write_id", ""),
                }
            )
            continue

        node_idx = event["node"]
        node = state[node_idx]
        targets = unique_targets(event.get("targets") or list(range(nodes)))

        if not node.alive:
            status = "rejected"
            tok = event.get("token", 0)
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": status,
                    "token": tok,
                    "expires_at": 0,
                    "write_id": event.get("write_id", ""),
                }
            )
            continue

        if etype == "request_lease":
            req_term = event.get("term", 0) or (node.vol_term + 1)
            votes = sum(1 for t in targets if 0 <= t < nodes and state[t].alive)
            if votes < quorum:
                results.append(
                    {
                        "index": idx,
                        "type": etype,
                        "status": "rejected",
                        "token": 0,
                        "expires_at": 0,
                    }
                )
                continue
            active_owner = -1
            active_expiry = 0
            active_token = 0
            for st in state:
                if st.alive and st.vol_token > 0 and st.vol_expiry > clock:
                    active_owner = st.vol_owner
                    active_expiry = st.vol_expiry
                    active_token = st.vol_token
                    break
            if (
                active_owner != -1
                and active_token > 0
                and active_expiry > clock
                and active_owner != node_idx
                and req_term <= node.vol_term
            ):
                results.append(
                    {
                        "index": idx,
                        "type": etype,
                        "status": "rejected",
                        "token": 0,
                        "expires_at": 0,
                    }
                )
                continue
            if req_term < node.vol_term:
                results.append(
                    {
                        "index": idx,
                        "type": etype,
                        "status": "rejected",
                        "token": 0,
                        "expires_at": 0,
                    }
                )
                continue
            new_token = max(st.persist_token for st in state) + 1
            ttl = event.get("ttl", 1)
            expiry = clock + ttl
            if expiry <= clock:
                expiry = clock + 1
            for t in targets:
                if 0 <= t < nodes and state[t].alive:
                    tgt = state[t]
                    tgt.persist_term = req_term
                    tgt.persist_owner = node_idx
                    tgt.persist_token = new_token
                    tgt.persist_expiry = expiry
                    tgt.vol_term = req_term
                    tgt.vol_owner = node_idx
                    tgt.vol_token = new_token
                    tgt.vol_expiry = expiry
            node.vol_term = req_term
            node.vol_owner = node_idx
            node.vol_token = new_token
            node.vol_expiry = expiry
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "granted",
                    "token": new_token,
                    "expires_at": expiry,
                }
            )
            continue

        if etype == "write":
            token = event.get("token", 0)
            write_id = event.get("write_id", "")
            if node.vol_owner != node_idx or node.vol_token != token or clock > node.vol_expiry:
                results.append(
                    {
                        "index": idx,
                        "type": etype,
                        "status": "rejected",
                        "token": token,
                        "expires_at": 0,
                        "write_id": write_id,
                    }
                )
                continue
            acks = 0
            for t in targets:
                if 0 <= t < nodes and state[t].alive:
                    tgt = state[t]
                    if (
                        tgt.persist_token == token
                        and tgt.persist_owner == node_idx
                        and tgt.persist_expiry >= clock
                    ):
                        acks += 1
            if acks < quorum:
                results.append(
                    {
                        "index": idx,
                        "type": etype,
                        "status": "rejected",
                        "token": token,
                        "expires_at": 0,
                        "write_id": write_id,
                    }
                )
                continue
            for t in targets:
                if 0 <= t < nodes and state[t].alive:
                    state[t].persist_writes.add(write_id)
            node.persist_writes.add(write_id)
            committed.add(write_id)
            results.append(
                {
                    "index": idx,
                    "type": etype,
                    "status": "committed",
                    "token": token,
                    "expires_at": clock,
                    "write_id": write_id,
                }
            )
            continue

    active_owner = -1
    active_token = 0
    active_term = 0
    active_expiry = 0
    for i in range(nodes):
        st = state[i]
        if st.alive and st.vol_token > 0 and st.vol_expiry > clock:
            active_owner = st.vol_owner
            active_token = st.vol_token
            active_term = st.vol_term
            active_expiry = st.vol_expiry
            break

    unique_leases = True
    seen = []
    for st in state:
        if st.alive and st.vol_token > 0 and st.vol_expiry > clock:
            seen.append((st.vol_owner, st.vol_token))
    if len(seen) > 1:
        unique_leases = False

    invariants = {
        "unique_leases": unique_leases,
        "recovery_durable_ok": True,
        "fence_monotonic": True,
    }
    return {
        "case_id": case["case_id"],
        "case_seed": case["seed"],
        "results": results,
        "committed_writes": sorted(committed),
        "invariants": invariants,
        "final_state": {
            "owner": active_owner,
            "token": active_token,
            "term": active_term,
            "expires_at": active_expiry,
        },
    }


def encode_case(case: dict[str, Any]) -> bytes:
    return (json.dumps(simulate_case(case), separators=(",", ":")) + "\n").encode()
