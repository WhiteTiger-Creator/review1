# Switch Failover

failures.json lists switches that are failed and cannot be used.

## Rules

1. The sequencer must never emit a THROW_SWITCH command for a failed switch.
2. When the preferred route uses a failed switch, the sequencer must find an alternative path through non-failed switches.
3. If no alternative path exists between two tracks (all connecting switches are failed), the sequencer must use intermediate tracks. For example, route through LEAD as a waypoint.
4. The closure checker must exclude failed switches when computing reachability from the locomotive's final position to LEAD.
5. Optimize validation must set capacity_verified to false whenever the emitted command list contains THROW_SWITCH against any failed switch id, even if occupancy inequalities alone would pass. Path search that skips failed edges is necessary but not sufficient; the validated artifact must still flag an injected or residual illegal throw through capacity_verified.
