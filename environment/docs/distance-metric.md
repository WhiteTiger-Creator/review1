# Geometric Path-Length Metric

Total trajectory length is the discrete geometric path integral of edge length along the emitted occupancy-dynamics movement trajectory:

    total_distance_m = sum_{c in commands, c.type in {PUSH,PULL,MOVE_LOCO}} length_m(c.from_track, c.to_track)

Each movement traverses exactly one switch edge. The distance for that movement equals the length_m of the traversed edge between from_track and to_track (matching the switch that connects those tracks in topology.json).

Using hop count (1 per move) instead of edge.length_m is incorrect. Different switch edges have different physical lengths, and the distance metric must reflect actual track geometry.

## Graded contract (not plan optimization)

Scoring checks that total_distance_m equals an independent length_m sum over the emitted movement commands for that sequence. Any capacity-feasible and closure-valid sequence is acceptable when its reported total_distance_m matches the length_m summation for its own commands. Scoring does not require a globally shortest plan, a minimal move count, or any other optimality ranking among feasible sequences.
