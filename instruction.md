We need an offline planner for a Linux systemd maintenance window. Given unit fragments, drop-ins, a live `systemctl`-style state snapshot, changed unit files, path and mount state, and a short maintenance budget, produce the exact restart/reload/start/stop plan that should be run.

Complete the Go utility at `/workspace/cmd/systemd-window-plan/main.go` and build `/workspace/bin/systemd-window-plan`. Invoke it as:

`/workspace/bin/systemd-window-plan INPUT_JSON OUTPUT_JSON`

Both positional arguments are required. Read `INPUT_JSON`, create or replace `OUTPUT_JSON`, and create the output parent directory if needed. The public input is `/workspace/task_file/window_request.json`; the public output path is `/workspace/output/window_plan.json`.

The input schema, systemd fragment/drop-in precedence, action state transitions, dependency and conflict rules, mount/path rules, budget constraints, objective order, tie-breaks, output schema, reason strings, warning strings, ordering rules, and empty-output behavior are specified in `/workspace/task_file/docs/SPEC.md`. Follow that file exactly. Grading uses exact JSON equality after parsing, so field names, lowercase enum strings, array contents, sorting, 1-based operation steps, empty arrays, and reason order all matter.

The verifier reruns your utility on compatible hidden host snapshots. Those snapshots vary unit-file precedence, active versus inactive units, protected units, dependency closure, `PartOf=`, `PropagatesReloadTo=`, `RequiresMountsFor=`, path conditions, symmetric conflicts, weak wants, ordering cycles, and tight maintenance budgets.
