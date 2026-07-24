# YOD — Yard Occupancy Dynamics Model

YOD is the discrete dynamical model used for this numerical study. A classification yard is an undirected spatial graph G = (V, E). Track nodes carry physical capacity. Switch edges carry geometric length in meters.

## State variables

At each discrete step of an occupancy trajectory, every track t holds an ordered list of cars. The occupancy state is feasible only when both inequalities hold:

    n_cars(t) <= max_cars(t)
    sum_{c on t} length_units(c) <= max_length_units(t)

## Path-integral observable

Each movement that traverses a switch edge contributes that edge length_m to the trajectory observable:

    total_distance_m = sum_{move in {PUSH,PULL,MOVE_LOCO}} length_m(from_track, to_track)

Hop counting is not a valid geometric observable under YOD.

## Residual-graph closure

Failed switches delete edges from G. After the trajectory ends, loco_end_track must remain in the residual reachable set of LEAD under breadth-first search on the surviving edges. Ending on LEAD is sufficient. Ending elsewhere is valid only when a residual path to LEAD still exists.

## Destination-block partitions

Outbound occupancy partitions group cars by destination in plan destination_order. Within each destination block, cars preserve their relative inbound consist order (stable partition).
