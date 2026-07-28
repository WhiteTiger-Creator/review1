The ridge-ui offline release is blocked. Release engineering cut npm over to a new internal mirror last week, and the airgapped build now stops before it can finish—the step that turns the checked-in monorepo into a build plan exits without producing a usable result. Everything needed for that step already lives under `/app/`.

Finish `/app/bin/repair-lock.js` so the command below writes `/app/output/build-plan.json` from the bundled inputs. Full behavior and output requirements are in `/app/docs/mirror_contract.md`.

```bash
node /app/bin/repair-lock.js
```

Do not modify bundled inputs under `/app/`. The environment has no network access. Exit with code 0 after the output file is written successfully. Repeated runs on the same inputs must produce identical output bytes.
