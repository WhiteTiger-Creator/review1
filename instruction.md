Release engineering moved the npm mirror last week and the offline build for `/app/workspace` now fails on a stale lock snapshot. Finish `/app/bin/repair-lock.js` so it reads the bundled workspace, registry, and policy under `/app/`, follows `/app/docs/mirror_contract.md`, and writes `/app/output/build-plan.json`.

```
node /app/bin/repair-lock.js
```

All resolution rules and output schema are defined in `/app/docs/mirror_contract.md`. The build runs without network access. Do not modify bundled inputs under `/app/`. Exit with code 0 after successfully writing the output file. Repeated runs must produce identical output bytes.
