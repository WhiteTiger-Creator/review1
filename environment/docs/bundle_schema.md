# Hall bundle layout

Each hall directory under `estate/rosters/` carries four files.

`policy.toml` — flat keys plus one `[region_weights]` table:

```
eval_epoch          integer  evaluation epoch for the replay
min_nodes           integer  ready-node floor per rack
allowed_firmware    strings  permitted firmware revisions, empty means any
min_usable_tb       integer  usable capacity floor per rack
min_replicas        integer  replica-copy floor per rack
min_gbps            integer  line-rate floor for an uplink to count
min_healthy_links   integer  healthy uplinks required per rack
min_roles           integer  distinct approver roles required per rack
required_roles      strings  approver roles that must all be present
cool_epochs         integer  cool-down span after a service record
budget_kw           integer  hall power draw ceiling
allowed_classes     strings  permitted hardware classes, empty means any
```

`units.jsonl` — one rack per line:
`id`, `region`, `class`, `tier`, `ready_nodes`, `firmware`, `raw_tb`,
`degraded_tb`, `replicas`, `uplinks` (each `gbps` and `healthy`), `draw_kw`.

`approvals.jsonl` — one approval per line: `unit`, `role`, `expires_epoch`.

`maintenance.jsonl` — one service record per line: `unit`, `epoch`, `resolved`.
The file may be empty when a hall has no recorded service history.
