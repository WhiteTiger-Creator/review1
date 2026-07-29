"""Behavioral verifier for /app/bin/emsolve.

Authoring layout: sources are packaged under `/app/environment` and copied to `/app` at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest
from helpers.mesh_factory import (
    deterministic_perm,
    permute_boundary_vertices,
    permute_corner_vertices,
    reorder_elements,
    reverse_local_orientation,
    stretched_cavity_mesh,
    unit_cube_mesh,
)
from helpers.operator_checks import compare_clustered_spectra
from helpers.run_solver import load_modes, run_solver

APP_DIR = Path("/app")
BIN = APP_DIR / "bin" / "emsolve"
DATA = APP_DIR / "data"
MANIFEST = Path("/tests/fixtures/immutable_manifest.json")
SCHEMA = Path("/tests/fixtures/consumer_schema.json")
CANONICAL_MESH = DATA / "meshes" / "cavity_canonical.mesh"
INVALID_MESH = DATA / "meshes" / "invalid_nonmanifold.mesh"

BOUNDARY_TOL = 1e-8
DIVERGENCE_TOL = 1e-7
ALGEBRAIC_TOL = 1e-6


@pytest.fixture(scope="session", autouse=True)
def rebuild_solver() -> None:
    """Force a clean rebuild so patched sources are exercised."""
    shutil.rmtree("/app/build", ignore_errors=True)
    subprocess.run(["/app/scripts/build.sh"], check=True)


def _assert_residuals(payload: dict) -> None:
    for mode in payload["modes"]:
        res = mode["residuals"]
        assert res["boundary_trace"] <= BOUNDARY_TOL
        assert res["divergence"] <= DIVERGENCE_TOL
        assert res["algebraic"] <= ALGEBRAIC_TOL


def _solve(mesh: Path, modes: int, output: Path, **kwargs) -> dict:
    proc = run_solver(mesh, modes, output, **kwargs)
    assert proc.returncode == 0, proc.stderr
    payload = load_modes(output)
    assert payload["computed_modes"] == modes
    _assert_residuals(payload)
    return payload


def test_canonical_mesh_physical_modes(tmp_path: Path) -> None:
  """Canonical cavity mesh yields finite modes within residual limits."""
  out = tmp_path / "canonical.json"
  payload = _solve(CANONICAL_MESH, 4, out)
  values = [m["eigenvalue"] for m in payload["modes"]]
  assert all(math.isfinite(v) and v > 0 for v in values)


def test_vertex_renumbering_invariance(tmp_path: Path) -> None:
  """Global vertex renumbering must not change the physical spectrum."""
  base = unit_cube_mesh()
  mesh_a = tmp_path / "a.mesh"
  mesh_b = tmp_path / "b.mesh"
  base.write(mesh_a)
  permute_corner_vertices(base, deterministic_perm(8, seed=17)).write(mesh_b)
  pa = _solve(mesh_a, 4, tmp_path / "a.json")
  pb = _solve(mesh_b, 4, tmp_path / "b.json")
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in pa["modes"]],
      [m["coefficients"] for m in pa["modes"]],
      [m["eigenvalue"] for m in pb["modes"]],
      [m["coefficients"] for m in pb["modes"]],
  )


def test_element_order_and_local_orientation_invariance(tmp_path: Path) -> None:
  """Element reordering and local orientation flips preserve physics."""
  base = unit_cube_mesh()
  mesh_ref = tmp_path / "ref.mesh"
  mesh_xform = tmp_path / "xform.mesh"
  base.write(mesh_ref)
  transformed = reverse_local_orientation(
      reorder_elements(base, list(reversed(range(len(base.elements))))),
      [0, 2, 4, 6, 8, 10],
  )
  transformed.write(mesh_xform)
  pa = _solve(mesh_ref, 4, tmp_path / "ref.json")
  pb = _solve(mesh_xform, 4, tmp_path / "xform.json")
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in pa["modes"]],
      [m["coefficients"] for m in pa["modes"]],
      [m["eigenvalue"] for m in pb["modes"]],
      [m["coefficients"] for m in pb["modes"]],
  )


def test_boundary_face_order_invariance(tmp_path: Path) -> None:
  """Boundary-face vertex ordering must not change elimination or spectra."""
  base = unit_cube_mesh()
  mesh_a = tmp_path / "a.mesh"
  mesh_b = tmp_path / "b.mesh"
  base.write(mesh_a)
  permute_boundary_vertices(base, [1, 2, 0] * 4).write(mesh_b)
  pa = _solve(mesh_a, 4, tmp_path / "a.json")
  pb = _solve(mesh_b, 4, tmp_path / "b.json")
  assert pa["active_dofs"] == pb["active_dofs"]
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in pa["modes"]],
      [m["coefficients"] for m in pa["modes"]],
      [m["eigenvalue"] for m in pb["modes"]],
      [m["coefficients"] for m in pb["modes"]],
  )


def test_clean_resume_equivalence(tmp_path: Path) -> None:
  """Checkpoint resume must match an uninterrupted solve."""
  mesh = tmp_path / "mesh.mesh"
  unit_cube_mesh().write(mesh)
  clean_out = tmp_path / "clean.json"
  ckpt = tmp_path / "state.bin"
  resumed_out = tmp_path / "resumed.json"
  clean = _solve(mesh, 4, clean_out)
  proc = run_solver(mesh, 4, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
  assert proc.returncode == 0, proc.stderr
  resumed = _solve(mesh, 4, resumed_out, resume=ckpt)
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in clean["modes"]],
      [m["coefficients"] for m in clean["modes"]],
      [m["eigenvalue"] for m in resumed["modes"]],
      [m["coefficients"] for m in resumed["modes"]],
  )


def test_checkpoint_remap_on_equivalent_numbering(tmp_path: Path) -> None:
  """Checkpoints created on one numbering must resume on equivalent meshes."""
  base = unit_cube_mesh()
  mesh_a = tmp_path / "a.mesh"
  mesh_b = tmp_path / "b.mesh"
  base.write(mesh_a)
  permute_corner_vertices(base, deterministic_perm(8, seed=99)).write(mesh_b)
  ckpt = tmp_path / "state.bin"
  proc = run_solver(mesh_a, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
  assert proc.returncode == 0, proc.stderr
  direct = _solve(mesh_b, 4, tmp_path / "direct.json")
  resumed = _solve(mesh_b, 4, tmp_path / "resumed.json", resume=ckpt)
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in direct["modes"]],
      [m["coefficients"] for m in direct["modes"]],
      [m["eigenvalue"] for m in resumed["modes"]],
      [m["coefficients"] for m in resumed["modes"]],
  )


def test_incompatible_checkpoint_rejected_without_output_corruption(tmp_path: Path) -> None:
  """Incompatible checkpoints must fail without writing valid output."""
  mesh_a = tmp_path / "a.mesh"
  mesh_b = tmp_path / "b.mesh"
  unit_cube_mesh().write(mesh_a)
  stretched_cavity_mesh((1.2, 1.0, 1.0)).write(mesh_b)
  ckpt = tmp_path / "state.bin"
  proc = run_solver(mesh_a, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
  assert proc.returncode == 0, proc.stderr
  bad_out = tmp_path / "bad.json"
  bad = run_solver(mesh_b, 4, bad_out, resume=ckpt)
  assert bad.returncode > 0
  if bad_out.exists():
    payload = json.loads(bad_out.read_text(encoding="utf-8"))
    assert payload.get("computed_modes", 0) < 1


def test_clustered_eigenspace_equivalence(tmp_path: Path) -> None:
  """Repeated modes are compared by subspace, not component-wise vectors."""
  base = unit_cube_mesh()
  mesh_a = tmp_path / "a.mesh"
  mesh_b = tmp_path / "b.mesh"
  base.write(mesh_a)
  permute_corner_vertices(base, deterministic_perm(8, seed=5)).write(mesh_b)
  pa = _solve(mesh_a, 6, tmp_path / "a.json")
  pb = _solve(mesh_b, 6, tmp_path / "b.json")
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in pa["modes"]],
      [m["coefficients"] for m in pa["modes"]],
      [m["eigenvalue"] for m in pb["modes"]],
      [m["coefficients"] for m in pb["modes"]],
      angle_tol=0.08,
  )


def test_mode_count_and_higher_mode_regression(tmp_path: Path) -> None:
  """Requested mode counts must be honored on multiple geometries."""
  for modes in (2, 4, 6):
    mesh = tmp_path / f"m{modes}.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, modes, tmp_path / f"out{modes}.json")
    assert payload["requested_modes"] == modes
    assert len(payload["modes"]) == modes


def test_cli_and_schema_compatibility(tmp_path: Path) -> None:
  """Public CLI flags and JSON schema remain stable."""
  help_proc = subprocess.run([str(BIN), "--help"], text=True, capture_output=True, check=False)
  assert help_proc.returncode == 0
  for flag in ("--mesh", "--modes", "--output", "--checkpoint", "--checkpoint-after", "--resume"):
    assert flag in help_proc.stdout
  out = tmp_path / "schema.json"
  payload = _solve(CANONICAL_MESH, 4, out, checkpoint_after=None)
  schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
  jsonschema.validate(instance=payload, schema=schema)


def test_invalid_mesh_error_regression(tmp_path: Path) -> None:
  """Malformed meshes must exit nonzero without valid mode output."""
  out = tmp_path / "bad.json"
  proc = run_solver(INVALID_MESH, 4, out)
  assert proc.returncode > 0
  if out.exists():
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("computed_modes", 0) < 1


def test_visible_fixture_integrity() -> None:
  """Visible /app/data assets must match verifier-owned SHA-256 checksums."""
  manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
  for rel, digest in manifest["files"].items():
    path = DATA / rel
    assert path.exists(), rel
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == digest, rel


def test_fresh_copy_behavior(tmp_path: Path) -> None:
  """Independent working copies of the built solver must agree on generated meshes."""
  mesh = tmp_path / "gen.mesh"
  unit_cube_mesh().write(mesh)
  copy_a = tmp_path / "copy_a"
  copy_b = tmp_path / "copy_b"
  for dst in (copy_a, copy_b):
    shutil.copytree(APP_DIR, dst, ignore=shutil.ignore_patterns("build"))
    shutil.copy2(BIN, dst / "bin" / "emsolve")
  out_a = tmp_path / "a.json"
  out_b = tmp_path / "b.json"
  for dst, out in ((copy_a, out_a), (copy_b, out_b)):
    proc = subprocess.run(
      [str(dst / "bin" / "emsolve"), "--mesh", str(mesh), "--modes", "4", "--output", str(out)],
      text=True,
      capture_output=True,
      check=False,
    )
    assert proc.returncode == 0, proc.stderr
  pa = load_modes(out_a)
  pb = load_modes(out_b)
  assert compare_clustered_spectra(
      [m["eigenvalue"] for m in pa["modes"]],
      [m["coefficients"] for m in pa["modes"]],
      [m["eigenvalue"] for m in pb["modes"]],
      [m["coefficients"] for m in pb["modes"]],
  )
