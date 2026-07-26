Our quantum-chemistry workflow needs a reliable native Go executable implementing a deterministic parallel Boys orbital-localization sweep. It must compute an exact K-best frontier of compatible Jacobi-rotation plans under per-sweep work limits, scale to dense 20-orbital planning cases, update the three dipole matrices from the winning plan, and retain an auditable convergence and optimality trace.

The executable must be located at `/app/bin/boys-localization-sweep` and accept exactly two positional arguments: an input JSON path and an output JSON path. For example:

```bash
/app/bin/boys-localization-sweep /app/fixtures/public.json /app/out/public_result.json
```

The executable must handle every compatible fixture described by `/app/docs/numerical_spec.md`; the public fixture is only an example. That document is the complete input schema, rotation and plan-selection contract, validation and failure behavior, output schema, numerical tolerance, ordering, and tie-break contract. Relative paths are not involved. The executable must not alter its input, and any invalid input or numerical failure must exit nonzero without creating or replacing a successful output.
