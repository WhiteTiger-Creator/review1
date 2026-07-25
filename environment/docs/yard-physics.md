# Yard Occupancy Physics (YOD)

This document expands the Yard Occupancy Dynamics (YOD) discrete dynamical model introduced in /app/docs/yod-model.md. A classification yard is an undirected spatial graph G = (V, E). Track nodes V carry physical capacity. Switch edges E carry geometric traversal length used in the path-integral observable.

## Occupancy inequalities

After every PUSH or PULL that changes track t, both inequalities must hold:

    n_cars(t) <= max_cars(t)
    sum_{c on t} length_units(c) <= max_length_units(t)

Violating either inequality is an infeasible occupancy state. The solver must choose alternate classification tracks or intermediate lead hops so both invariants remain true at every intermediate step.

## Geometric path integral

Each switch edge e carries length_m(e) in meters. For a movement command that traverses the undirected edge between from_track and to_track:

    cost(move) = length_m(from_track, to_track)

The scalar trajectory length is the discrete path integral:

    total_distance_m = sum_{move in {PUSH,PULL,MOVE_LOCO}} cost(move)

Hop counting (one per move) is not a valid geometric metric. Scoring checks geometric accounting on the emitted sequence, not selection of a globally shortest plan among feasible alternatives.

## Closure reachability

Let E_fail be the set of switch ids listed in failures.json. The residual graph deletes those edges. After the sequence completes, loco_end_track must admit a path to LEAD in the residual graph (breadth-first search). Ending on LEAD is sufficient but not required. Isolated endpoints with no residual path to LEAD leave closure_verified false.

## Failed-switch edge deletion

THROW_SWITCH must never target an edge in E_fail. When a direct edge is gone, sequences may route through intermediate nodes such as LEAD when those residual paths remain open.

## capacity_verified in shunting-validated.json

The optimize stage writes capacity_verified on the validated artifact at /app/state/shunting-validated.json (optimize output). That boolean is a single physics gate covering every capacity-feasibility check on the emitted command list. It is true only when all of the following hold:

1. Dual occupancy inequalities hold for every intermediate PUSH/PULL state under live sequencing and under optimize-stage replay.
2. No emitted THROW_SWITCH command targets a switch_id listed in failures.json (E_fail).

If any THROW_SWITCH references a failed switch, capacity_verified must be false even when track occupancy counts and length sums alone would pass. Failed-switch throw checking is not a separate export-only advisory; it participates in the same capacity_verified flag as the occupancy inequalities.
