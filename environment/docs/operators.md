# operators

Cgroup memcg peak ops for systemd lane units on this host. Unit template: `/app/environment/systemd/hwm-unit@.service` (`MemoryAccounting=yes`, `ExecStart` installs `/app/bin/hwm_drive`).

Workspace prep:

```bash
bash /app/environment/scripts/prep_run.sh
```

Build and run the default cgroup-slice matrix (budget_cap 48):

```bash
bash /app/environment/scripts/drive_matrix.sh
```

Wide budget arm (budget_cap 96):

```bash
bash /app/environment/scripts/drive_matrix.sh --wide
```

Lane reset before a fresh matrix (slice migrate / recover):

```bash
bash /app/environment/migrations/mig9.sh
```

Equivalent direct driver (same binary the unit ExecStart invokes):

```bash
go build -o /app/bin/hwm_drive /app/environment/cmd/hwm_drive
/app/bin/hwm_drive --root /app/environment --out /app/output/peak_report.json
```

Independent rebuild used during grading may land at `/tmp/verifier-hwm_drive`.

Roster patch schedules live under `/app/environment/fixtures/roster/`. Membership maps under `/app/environment/fixtures/members/`.
