# Residual-Graph Closure Physics

After failed-switch edge deletion, the residual yard graph is a discrete dynamical system whose reachable set must still admit locomotive closure to LEAD.

## Locomotive Closure

After the occupancy trajectory completes, the locomotive must retain numerical reachability to LEAD over non-failed switches. LEAD is a residual-graph closure target, not a required final parking track.

- Ending on LEAD is sufficient.
- Ending on any other track is valid when a path from loco_end_track to LEAD still exists after excluding failed switches.
- Scoring must not require loco_end_track to equal LEAD.

If the locomotive ends on a track from which LEAD is not reachable via non-failed switches, the sequence is invalid and closure_verified must be false.

The closure check performs a graph reachability search from loco_end_track to LEAD, excluding any switch edges whose switch_id appears in failures.json.

## Dead-End Avoidance

A track that becomes isolated after failed-switch deletion has no remaining path to LEAD. The sequence must not leave the locomotive on such a track. Closure is reachability after failures are applied, not a requirement to finish parked on LEAD.
