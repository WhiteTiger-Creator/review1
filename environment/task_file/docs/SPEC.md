# systemd maintenance window planner contract

The input is one JSON object. Unknown top-level fields must be ignored.

Required top-level fields:

- `maintenance`: object with `deadline_sec` integer, `max_stopped_active` integer, `mount_start_limit` integer, `daemon_reload_sec` integer, `request_units` array of strings, and `protected_units` array of strings.
- `fragments`: array of unit fragment objects.
- `runtime`: array of runtime unit objects.
- `paths`: array of path objects.
- `changes`: array of changed file objects.

Fragment objects use this schema:

- `path`: string, absolute path.
- `unit`: string, canonical unit name.
- `kind`: lowercase string, either `base` or `dropin`.
- `source`: lowercase string, one of `vendor`, `runtime`, or `admin`.
- `dropin`: string. It is required for `dropin` fragments and must be `""` for `base` fragments.
- `reset`: array of directive names. Missing means `[]`.
- `directives`: object. Missing directive fields use the defaults below.

Runtime objects use this schema:

- `unit`: string.
- `load_state`: lowercase string, one of `loaded`, `masked`, or `not-found`.
- `active_state`: lowercase string, one of `active`, `inactive`, or `failed`.

Path objects use this schema:

- `path`: string, absolute path.
- `exists`: boolean.
- `mount_unit`: string. Use `""` when no mount unit is known for the path.

Change objects use this schema:

- `path`: string, absolute path.
- `unit`: string.
- `impact`: lowercase string, one of `restart`, `reload`, or `none`.
- `priority`: integer. Priorities are additive per unit.

Directive defaults:

- List directives default to `[]`: `requires`, `wants`, `after`, `before`, `conflicts`, `part_of`, `propagates_reload_to`, `requires_mounts_for`, and `condition_paths`.
- Scalar directives default to: `reloadable=false`, `refuse_manual_start=false`, `start_sec=1`, `stop_sec=1`, and `reload_sec=1`.

Fragment precedence:

- Source priority is `admin` highest, then `runtime`, then `vendor`.
- For a unit base fragment, only the highest-priority source is used. If two base fragments for the same unit have the same source, use the lexicographically smallest `path`.
- For drop-ins, compare by `(unit, dropin)`. For each pair, keep only the highest-priority source. If two kept candidates have the same source, use the lexicographically smallest `path`.
- Apply the selected base first, then selected drop-ins in lexicographic `dropin` name order.
- For a drop-in, first process every name in `reset`, sorted lexicographically. A reset clears that list directive before the drop-in appends its values. Resets for scalar directives have no effect.
- List directive values are treated as sets after all fragments are applied. Sort them lexicographically for all later decisions. Scalar directives use the last applied value.
- Only the final materialized directives after base selection, selected drop-ins, resets, de-duplication, and sorting participate in planning. Values from shadowed fragments or values removed by a later reset have no effect on dependencies, conflicts, ordering, paths, or warnings except for inactive-change warnings on their own changed paths.

Active changes and warnings:

- A change is active only when its `path` is the selected base path for its unit or the selected path for one of that unit's kept drop-ins.
- Every inactive change must produce one warning object with `code="shadowed_change"`, that change's `unit`, and that change's `path`.
- Warnings are additive, one per inactive change. Warnings do not short-circuit other changes on the same unit.
- Inactive changes do not set `daemon_reloaded`, do not contribute priority, and do not create or modify root candidates.
- An active change with `impact="none"` requires a daemon reload but does not create a unit action candidate.
- `daemon_reloaded` is true when at least one active change exists. If it is true, the first operation must be `daemon-reload` with `unit=""`, `duration_sec=maintenance.daemon_reload_sec`, and `reasons=["active_change"]`.

Runtime and startability:

- Runtime state overrides fragment presence only for `masked` and `not-found`: a unit with runtime `load_state` `masked` or `not-found` is not startable even if it has a selected base.
- A unit is startable when it has a selected base, runtime `load_state` is absent or `loaded`, and `refuse_manual_start=false`.
- A runtime `active_state` of `failed` is treated as inactive for planning.
- A protected unit may be reloaded, but it may not be stopped, restarted, or started.

Root change candidates:

- Group active `restart` and `reload` changes by `unit`. The grouped unit priority is the sum of grouped change priorities.
- `restart` dominates `reload` for the grouped unit action. If both impacts exist, the root action is `restart` and both `changed_restart` and `changed_reload` reasons apply.
- If the changed unit is active, it is a root candidate.
- If the changed unit is inactive or failed, it is a root candidate only when its name appears in `maintenance.request_units`; its operation is `start`.
- If the changed unit is inactive or failed and is not requested, it must appear in `units` with `planned_action="unchanged"`, `applied_change=false`, `final_state` equal to the input active state except `failed` remains `failed`, and reasons `["inactive_changed"]`.
- A protected root requiring `restart` or `start` is not selectable and must appear with `planned_action="unchanged"`, `applied_change=false`, and reason `["protected"]`. A protected reload root is selectable if it remains a reload.
- If a selected reload root is not reloadable, its operation becomes `restart` and the `reload_escalated` reason is added. If that escalation would restart a protected unit, the root is not selectable.
- `reload_escalated` is emitted only when a selected `reload` action becomes `restart` because the materialized unit is not reloadable. A root action that is already `restart` because a grouped `restart` impact dominates a grouped `reload` impact keeps `changed_restart` and `changed_reload` but does not get `reload_escalated` for that dominance alone.

Closure rules:

- Reasons are additive per unit and per operation. Use the reason order listed below and never emit duplicates.
- `restart` dominates `reload`, `reload` dominates `start`, and all of them dominate `unchanged`. `stop` is separate and is used only for conflict stops.
- Selecting a restart for unit `U` also selects a restart for each active unit `V` whose materialized `part_of` contains `U`; `V` gets reason `part_of`.
- Selecting a reload for unit `U` also selects a reload for each active unit named in `U`'s materialized `propagates_reload_to`; the propagated unit gets reason `propagated_reload`. If the propagated unit is not reloadable, that action escalates to restart and gets `reload_escalated`.
- For any selected `start` or `restart`, every materialized `requires` unit must be active by the start phase. An inactive required unit is added with operation `start` and reason `required_dependency`.
- For any selected `start` or `restart`, every `requires_mounts_for` path must exist by the start phase. If the path does not exist and has a non-empty `mount_unit`, the mount unit is added with operation `start` and reason `requires_mounts_for`. Starting a mount makes all input paths with that `mount_unit` exist for later condition checks.
- After required mount starts are considered, every `condition_paths` path for a selected `start` or `restart` must exist. If not, the candidate plan is infeasible.
- If an inactive required unit or required mount is not startable, the candidate plan is infeasible.
- `wants` are weak. For a selected or derived unit, each inactive wanted unit may be started when it is startable and its own required closure is feasible. Wanted starts get reason `wanted_dependency`. Omitting a wanted start is allowed; plan selection decides by the objective below.
- Included wanted units are ordinary selected actions for closure, conflicts, ordering, durations, mount-start counting, and final state. A wanted start whose complete closure is infeasible cannot be included. Because wants are optional, a feasible plan may omit any wanted start.

Every complete candidate plan must be closed under all closure rules. Actions introduced by closure rules have the same closure obligations as root actions. `condition_paths` validity is evaluated against the complete candidate plan after applying all selected mount `start` and `restart` actions; an input path with `exists=false` exists in that plan when its non-empty `mount_unit` is active after the plan.

For `requires` and `requires_mounts_for`, add the corresponding reason only when that rule adds or upgrades the target unit action. If the dependency or path is already satisfied by the complete candidate plan, that rule adds no reason. When a mount unit is started to make a `requires_mounts_for` path exist, its reason is `requires_mounts_for`; this remains true when the same mount unit is also listed in `requires`. Use `required_dependency` for unit dependencies that are not being started to satisfy a `requires_mounts_for` path.

Conflicts:

- `Conflicts=` is symmetric. If either unit names the other in `conflicts`, the two units conflict.
- For any selected `start` or `restart`, every active conflicting unit must be stopped first unless that conflicting unit is also selected for `start`, `restart`, or `reload`. Selecting both sides of an active conflict is infeasible.
- A protected conflicting unit cannot be stopped, so the candidate plan is infeasible.
- A conflict stop gets operation `stop`, final state `inactive`, and reason `conflict_stop`.
- Conflict stops are final for this plan. A unit stopped only because of a conflict may not be restarted later in the same plan.

Budgets:

- `elapsed_sec` is the sum of every operation's `duration_sec`, including daemon reload.
- Operation durations are: `start=start_sec`, `stop=stop_sec`, `reload=reload_sec`, and `restart=stop_sec+start_sec`.
- A plan is feasible only when `elapsed_sec <= maintenance.deadline_sec`.
- A plan is feasible only when the number of conflict-stopped units that were active in the input is `<= maintenance.max_stopped_active`.
- A plan is feasible only when the number of started units ending in `.mount` is `<= maintenance.mount_start_limit`.

Budget constraints apply to the complete candidate operation list after selected roots, closure rules, included weak wants, conflict stops, and ordering validity are resolved. The `mount_start_limit` counts every operation with `action` `start` or `restart` and a unit name ending in `.mount`, including operations introduced by dependencies or weak wants.

Ordering:

- Operation steps are 1-based and contiguous.
- If present, `daemon-reload` is step 1.
- Conflict `stop` operations come after daemon reload and are sorted by unit name.
- All `start`, `reload`, and `restart` operations come after stops. Order them with systemd-style ordering edges among touched units: `After=X` means `X` before this unit; `Before=X` means this unit before `X`; a required unit must be before the unit that requires it; a mount unit named by an input path used in `RequiresMountsFor=` must be before the unit using that path; a unit with `PropagatesReloadTo=X` must be before `X` when both reload or restart actions are touched. Ties use unit name. A cycle among touched units makes that candidate plan infeasible.
- `reload` and `restart` operations for active changed units are ordered by the same touched-unit graph. There is no separate stop/start expansion for a restart operation in output.

Plan objective and tie-break:

Choose one feasible complete final plan. Compare complete plans in this exact order:

1. Maximize `applied_priority`, the sum of priorities of selected root change units. A root change unit is selected when the complete final plan contains a `start`, `reload`, or `restart` operation that satisfies its grouped root action, even if that operation was introduced by dependency or propagation closure.
2. Maximize `applied_units`, the number of selected root change units.
3. Maximize `final_active_units`, the number of units from the union of runtime units and materialized units whose final state is `active`.
4. Minimize `elapsed_sec`.
5. Minimize `stopped_active_units`, the number of input-active units left inactive by conflict stops.
6. Use the lexicographically smallest operation signature. The signature is the ordered array of `action + ":" + unit` strings for the complete operation list, including `daemon-reload:`.

The tie-break compares complete final plans, not local candidates.

Output schema:

- Write one JSON object with exactly these keys: `daemon_reloaded`, `objective`, `operations`, `units`, and `warnings`.
- `daemon_reloaded`: boolean.
- `objective`: object with exactly integer keys `applied_priority`, `applied_units`, `final_active_units`, `elapsed_sec`, and `stopped_active_units`.
- `operations`: array of objects sorted by execution step. Each operation has exactly `step` integer, `action` string, `unit` string, `duration_sec` integer, and `reasons` array of strings.
- `units`: array sorted by `name`. Include every unit that is a grouped active changed unit, every inactive changed unit, and every unit touched by a selected operation. Each object has exactly `name`, `planned_action`, `applied_change`, `final_state`, and `reasons`.
- `warnings`: array sorted by `unit`, then `path`, then `code`. Each warning has exactly `code`, `unit`, and `path`.
- Every array-valued field in the output schema must be encoded as a JSON array. When it has no elements, encode it as `[]`, not `null`.

Valid operation actions are `daemon-reload`, `stop`, `start`, `reload`, and `restart`. Valid unit `planned_action` values are `stop`, `start`, `reload`, `restart`, `unchanged`, and `deferred`. A root change unit that is not selected must use `planned_action="deferred"` and reason `not_selected`, unless it has the documented `inactive_changed` or `protected` result, or unless it is touched by a selected operation for another reason. In that touched case, report the actual operation as `planned_action` and add `not_selected` to the other operation reasons.

Final states are `active`, `inactive`, `failed`, `masked`, and `not-found`. Units not touched by operations keep their input final state, except absent runtime state defaults to `inactive`. Successful `start`, `reload`, and `restart` end `active`; successful `stop` ends `inactive`.

Reason order is:

1. `changed_restart`
2. `changed_reload`
3. `reload_escalated`
4. `requested_start`
5. `part_of`
6. `propagated_reload`
7. `required_dependency`
8. `wanted_dependency`
9. `requires_mounts_for`
10. `conflict_stop`
11. `inactive_changed`
12. `protected`
13. `not_selected`

Only these warning codes are valid: `shadowed_change`.

If there are no feasible root actions, still emit daemon reload if any active change exists, warnings, deferred or unchanged unit rows for changed units, and an objective with all counters derived from that final empty-action plan.
