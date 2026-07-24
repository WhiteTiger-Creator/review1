# x7 continuum environment

C++ MPI/HDF5 adaptive diffusion restart stack on the canonical
`public.ecr.aws/docker/library/gcc:13-bookworm` runtime with system OpenMPI and
HDF5. Builds `x7_orch` via CMake (`/app/environment/scripts/build_x7.sh`) and
seeds offline checkpoint fixtures (`/app/environment/scripts/seed_ckpts.sh`).
The binary installs to `/app/environment/bin/x7_orch`.

Public entry:

```bash
bash /app/environment/h1/run_x7.sh
/app/environment/tools/x7_gate --matrix-full --out /app/output/run-record.json --final /app/output/final.h5
```

Observation schema: `/app/environment/docs/restart_contract.md`.
