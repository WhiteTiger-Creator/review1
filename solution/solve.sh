#!/usr/bin/env bash
set -euo pipefail

solution_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
reference_src="${solution_dir}/reference/src"

install -m 0644 "${solution_dir}/reference/checkpoint.hpp" "/app/emsolve/include/emsolve/checkpoint.hpp"
for file in assembly.cpp checkpoint.cpp diagnostics.cpp eigensolver.cpp mesh.cpp modes.cpp topology.cpp; do
  install -m 0644 "${reference_src}/${file}" "/app/emsolve/src/${file}"
done

mkdir -p /output /app/bin
/app/scripts/build.sh

/app/bin/emsolve --mesh /app/data/meshes/cavity_canonical.mesh --modes 4 --output /output/modes.json
/app/bin/emsolve --mesh /app/data/meshes/cavity_vertex_permuted.mesh --modes 4 --output /tmp/permuted.json

python3 - <<'PY'
import json
from pathlib import Path

ZERO_TOL = 1e-8
SCALE = 1.7


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def compare_eigenvalues(a: dict, b: dict) -> None:
    va = [m["eigenvalue"] for m in a["modes"]]
    vb = [m["eigenvalue"] for m in b["modes"]]
    if len(va) != len(vb):
        raise SystemExit("oracle smoke: mode count mismatch")
    for i, (x, y) in enumerate(zip(va, vb)):
        if abs(x - y) > 1e-5:
            raise SystemExit(f"oracle smoke: eigenvalue mismatch at {i}")


def check_positive_physical_modes(payload: dict) -> None:
    if not payload["modes"]:
        raise SystemExit("oracle smoke: no modes reported")
    scale = max(1.0, max(abs(m["eigenvalue"]) for m in payload["modes"]))
    threshold = ZERO_TOL * scale
    first = payload["modes"][0]["eigenvalue"]
    if first <= threshold:
        raise SystemExit(f"oracle smoke: first mode is non-physical ({first} <= {threshold})")
    for mode in payload["modes"]:
        if mode["eigenvalue"] <= threshold:
            raise SystemExit("oracle smoke: reported a null-space mode")
        if mode["residuals"]["algebraic"] > 1e-6:
            raise SystemExit("oracle smoke: algebraic residual too large")
        if mode["residuals"]["boundary_trace"] > 1e-8:
            raise SystemExit("oracle smoke: boundary_trace residual too large")
        if mode["residuals"]["divergence"] > 1e-7:
            raise SystemExit("oracle smoke: divergence residual too large")


canonical = load(Path("/output/modes.json"))
permuted = load(Path("/tmp/permuted.json"))
compare_eigenvalues(canonical, permuted)
check_positive_physical_modes(canonical)

# Simple uniform-scale smoke: eigenvalues should scale approximately by 1/s^2.
def scale_mesh_text(text: str, factor: float) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.startswith("vertices "):
            count = int(line.split()[1])
            for _ in range(count):
                i += 1
                vid, x, y, z = lines[i].split()
                out.append(
                    f"{vid} {float(x) * factor} {float(y) * factor} {float(z) * factor}"
                )
        i += 1
    return "\n".join(out) + "\n"


base_mesh = Path("/tmp/oracle_base.mesh")
scaled_mesh = Path("/tmp/oracle_scaled.mesh")
canonical_mesh = Path("/app/data/meshes/cavity_canonical.mesh")
base_mesh.write_text(canonical_mesh.read_text())
scaled_mesh.write_text(scale_mesh_text(canonical_mesh.read_text(), SCALE))

out_base = Path("/tmp/oracle_base.json")
out_scaled = Path("/tmp/oracle_scaled.json")
import subprocess

subprocess.run(
    ["/app/bin/emsolve", "--mesh", str(base_mesh), "--modes", "3", "--output", str(out_base)],
    check=True,
)
subprocess.run(
    ["/app/bin/emsolve", "--mesh", str(scaled_mesh), "--modes", "3", "--output", str(out_scaled)],
    check=True,
)
base = load(out_base)
scaled = load(out_scaled)
check_positive_physical_modes(base)
check_positive_physical_modes(scaled)
for mb, ms in zip(base["modes"], scaled["modes"]):
    expected = mb["eigenvalue"] / (SCALE * SCALE)
    if abs(ms["eigenvalue"] - expected) / max(expected, 1e-12) > 1e-3:
        raise SystemExit("oracle smoke: scale law mismatch")

# Coefficient-level canonicalization across one representation-only transform.
combined_mesh = Path("/tmp/oracle_combined.mesh")
combined_mesh.write_text(Path("/app/data/meshes/cavity_vertex_permuted.mesh").read_text())
out_combined = Path("/tmp/oracle_combined.json")
subprocess.run(
    [
        "/app/bin/emsolve",
        "--mesh",
        str(combined_mesh),
        "--modes",
        "6",
        "--output",
        str(out_combined),
    ],
    check=True,
)
canonical6 = load(Path("/output/modes.json"))
subprocess.run(
    [
        "/app/bin/emsolve",
        "--mesh",
        str(canonical_mesh),
        "--modes",
        "6",
        "--output",
        "/tmp/oracle_canonical6.json",
    ],
    check=True,
)
canonical6 = load(Path("/tmp/oracle_canonical6.json"))
combined = load(out_combined)
if len(combined["modes"]) != len(canonical6["modes"]):
    raise SystemExit("oracle smoke: combined mode count mismatch")
for ma, mb in zip(canonical6["modes"], combined["modes"]):
    if abs(ma["eigenvalue"] - mb["eigenvalue"]) > 1e-5:
        raise SystemExit("oracle smoke: combined eigenvalue mismatch")
    if max(abs(x - y) for x, y in zip(ma["coefficients"], mb["coefficients"])) > 1e-7:
        raise SystemExit("oracle smoke: canonical coefficient mismatch across transform")

# Checkpoint/resume smoke with coefficient agreement.
ckpt = Path("/tmp/oracle_ckpt.bin")
subprocess.run(
    [
        "/app/bin/emsolve",
        "--mesh",
        str(canonical_mesh),
        "--modes",
        "6",
        "--output",
        "/tmp/oracle_ckpt_partial.json",
        "--checkpoint",
        str(ckpt),
        "--checkpoint-after",
        "3",
    ],
    check=True,
)
subprocess.run(
    [
        "/app/bin/emsolve",
        "--mesh",
        str(canonical_mesh),
        "--modes",
        "6",
        "--output",
        "/tmp/oracle_resumed.json",
        "--resume",
        str(ckpt),
    ],
    check=True,
)
resumed = load(Path("/tmp/oracle_resumed.json"))
for ma, mb in zip(canonical6["modes"], resumed["modes"]):
    if max(abs(x - y) for x, y in zip(ma["coefficients"], mb["coefficients"])) > 1e-7:
        raise SystemExit("oracle smoke: resume coefficient mismatch")

print("oracle smoke ok")
PY
