Bridge-span screening in this checkout is producing bad mid-span deflection (mm) and support reaction (N) numbers for the offline case bundle.

Run `bash /app/environment/exec/kit.sh` to rebuild the Rust driver plus Go helper and regenerate `/app/output/span_parity.json`.

The verifier wipes that file and rebuilds from `/app/environment` before scoring.

Static or hand-edited JSON is insufficient; the normal pipeline must regenerate the artifacts.

Coarse-mesh results disagree with fine-mesh beyond `/app/environment/docs/tol_policy.md`.

Doubling every point force should nearly double deflection and reactions inside the published bands without moving load stations, but several cases break that.

A second identical kit pass drifts and leaves `fold_probe` dirty.

More than one helper behind the bash entrypoint is involved.

Schema and residual formulas are in `/app/environment/docs/report_contract.md`.

Inputs live under `/app/environment/cases/`.

The report must include `cases`, `tol_class`, `tol_limit`, `react_tol_limit`, `lin_tol_limit`, and `fold_probe`.

Fix the sources that feed the driver. Element formulation is not prescribed.
