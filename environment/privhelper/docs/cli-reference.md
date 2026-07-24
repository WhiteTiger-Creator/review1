# CLI reference

Entrypoint: `/app/bin/privhelper`

## reset

```text
privhelper reset --scenario ops-seal
```

Recreates runtime state from share fixtures: gen-1 signed manifest, trusted helpers under libexec, competing caller-bin artifacts, empty journal/decision/effect ledgers, clean reports.

## dispatch

```text
privhelper dispatch \
  --request ABSOLUTE_JSON_PATH \
  --via direct|job \
  [--caller-env ABSOLUTE_PATH] \
  [--trace ABSOLUTE_PATH] \
  [--crash-after prepared|effect]
```

Loads one request JSON, applies optional caller environment contamination for the process, authorizes against the current signed manifest, and runs the durable allow/deny/conflict flow.

## dispatch-batch

```text
privhelper dispatch-batch \
  --fixture ABSOLUTE_JSONL_PATH \
  --via direct|job \
  [--caller-env ABSOLUTE_PATH] \
  [--trace ABSOLUTE_PATH]
```

Dispatches each non-empty JSONL line as a request.

## manifest-install

```text
privhelper manifest-install --manifest ABSOLUTE_PATH --signature ABSOLUTE_PATH
```

Verifies Ed25519 signature, schema, scenario, and strictly increasing generation; atomically installs on success.

## recover

```text
privhelper recover --trace ABSOLUTE_PATH
```

Completes or denies pending journal work from durable evidence. Idempotent.

## resolved-helpers dump

```text
privhelper resolved-helpers dump --json [--caller-env ABSOLUTE_PATH]
```

Recomputes live helper trust under optional contamination and prints JSON probes.

## Exports

```text
privhelper journal-export --json
privhelper decisions-export --json
privhelper effects-export --json
```

## reconcile

```text
privhelper reconcile --trace ABSOLUTE_PATH --output ABSOLUTE_PATH
```

Independently verifies authority and writes the report schema plus a reconcile trace (includes a record with `"phase": "reconcile"`).

## selftest

```text
privhelper selftest --mode baseline
privhelper selftest --mode security
```

Runs against temporary/restored scenario state so the main incident ledger is not left corrupted.

- `baseline`: normal allowed owner seal; prints `SELFTEST_OK`
- `security`: contaminated helper lookup, denied principal, exact retry idempotency, and reconcile; prints `SECURITY_SELFTEST_OK` on success
