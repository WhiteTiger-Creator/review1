"""Deterministic tetrahedral cavity meshes for verifier-generated cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MeshData:
    vertices: list[tuple[float, float, float]]
    elements: list[tuple[int, int, int, int]]
    boundary: list[tuple[int, int, int, str]]

    def write(self, path: Path) -> None:
        lines = ["emsolve-mesh 1", f"vertices {len(self.vertices)}"]
        for idx, (x, y, z) in enumerate(self.vertices):
            lines.append(f"{idx} {x} {y} {z}")
        lines.append(f"elements {len(self.elements)}")
        for idx, tet in enumerate(self.elements):
            lines.append(f"{idx} {tet[0]} {tet[1]} {tet[2]} {tet[3]}")
        lines.append(f"boundary {len(self.boundary)}")
        for idx, face in enumerate(self.boundary):
            lines.append(f"{idx} {face[0]} {face[1]} {face[2]} {face[3]}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def unit_cube_mesh() -> MeshData:
    verts = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0, 0.0),
        (1.0, 0.0, 1.0),
        (0.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.5, 0.5, 0.5),
    ]
    elems = [
        (8, 3, 1, 0),
        (8, 5, 3, 1),
        (8, 2, 1, 0),
        (8, 4, 2, 1),
        (8, 3, 2, 0),
        (8, 6, 3, 2),
        (8, 5, 7, 3),
        (8, 6, 7, 3),
        (8, 4, 7, 2),
        (8, 6, 7, 2),
        (8, 5, 7, 1),
        (8, 4, 7, 1),
    ]
    boundary = [
        (2, 1, 0, "pec"),
        (4, 2, 1, "pec"),
        (6, 3, 2, "pec"),
        (6, 7, 2, "pec"),
        (3, 2, 0, "pec"),
        (6, 7, 3, "pec"),
        (4, 7, 1, "pec"),
        (5, 7, 1, "pec"),
        (3, 1, 0, "pec"),
        (5, 3, 1, "pec"),
        (4, 7, 2, "pec"),
        (5, 7, 3, "pec"),
    ]
    return MeshData(verts, elems, boundary)


def deterministic_perm(n: int, seed: int) -> list[int]:
    order = list(range(n))
    state = seed & 0xFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        j = state % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def permute_corner_vertices(mesh: MeshData, corner_perm: Sequence[int]) -> MeshData:
    center = len(mesh.vertices) - 1
    if len(corner_perm) != center:
        raise ValueError("corner_perm must cover every corner vertex")
    if sorted(corner_perm) != list(range(center)):
        raise ValueError("corner_perm must be a permutation of corner indices")
    # corner_perm[new_id] is the old vertex index relocated to new_id.
    verts = [mesh.vertices[corner_perm[i]] for i in range(center)] + [mesh.vertices[center]]
    old_to_new = {old: new for new, old in enumerate(corner_perm)}
    old_to_new[center] = center

    def map_vid(v: int) -> int:
        return old_to_new[v]

    elems = [tuple(map_vid(v) for v in tet) for tet in mesh.elements]
    boundary = [(*[map_vid(v) for v in face[:3]], face[3]) for face in mesh.boundary]
    return MeshData(verts, elems, boundary)


def reorder_elements(mesh: MeshData, order: Sequence[int]) -> MeshData:
    if len(order) != len(mesh.elements):
        raise ValueError("order must permute every element index")
    elems = [mesh.elements[i] for i in order]
    return MeshData(mesh.vertices, elems, mesh.boundary)


def reverse_local_orientation(mesh: MeshData, element_ids: Sequence[int]) -> MeshData:
    elems = list(mesh.elements)
    for eid in element_ids:
        a, b, c, d = elems[eid]
        elems[eid] = (a, b, d, c)
    return MeshData(mesh.vertices, elems, mesh.boundary)


def permute_boundary_vertices(mesh: MeshData, face_perm: Sequence[int]) -> MeshData:
    if len(face_perm) != len(mesh.boundary):
        raise ValueError("face_perm must cover every boundary face")
    boundary = []
    for idx, face in enumerate(mesh.boundary):
        rot = face_perm[idx] % 3
        v0, v1, v2, tag = face
        verts = [v0, v1, v2]
        rotated = verts[rot:] + verts[:rot]
        boundary.append((rotated[0], rotated[1], rotated[2], tag))
    return MeshData(mesh.vertices, mesh.elements, boundary)


def stretched_cavity_mesh(scale: tuple[float, float, float]) -> MeshData:
    sx, sy, sz = scale
    base = unit_cube_mesh()
    verts = [(x * sx, y * sy, z * sz) for x, y, z in base.vertices]
    return MeshData(verts, base.elements, base.boundary)


def _all_tetra_permutations() -> tuple[tuple[int, int, int, int], ...]:
  perms: list[tuple[int, int, int, int]] = []
  for a in range(4):
    for b in range(4):
      if b == a:
        continue
      for c in range(4):
        if c in (a, b):
          continue
        d = next(iter({0, 1, 2, 3} - {a, b, c}))
        perms.append((a, b, c, d))
  return tuple(perms)


TETRA_VERTEX_PERMUTATIONS = _all_tetra_permutations()


def apply_local_vertex_perm(
    mesh: MeshData, element_ids: Sequence[int], local_perm: Sequence[int]
) -> MeshData:
    if len(local_perm) != 4:
        raise ValueError("local_perm must have length 4")
    elems = list(mesh.elements)
    for eid in element_ids:
        tet = elems[eid]
        elems[eid] = tuple(tet[i] for i in local_perm)
    return MeshData(mesh.vertices, elems, mesh.boundary)


def mixed_local_permutations(mesh: MeshData, seed: int) -> MeshData:
    elems = list(mesh.elements)
    state = seed & 0xFFFFFFFF
    for eid in range(len(elems)):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        perm = TETRA_VERTEX_PERMUTATIONS[state % len(TETRA_VERTEX_PERMUTATIONS)]
        tet = elems[eid]
        elems[eid] = tuple(tet[i] for i in perm)
    return MeshData(mesh.vertices, elems, mesh.boundary)


def scale_uniform(mesh: MeshData, factor: float) -> MeshData:
    verts = [(x * factor, y * factor, z * factor) for x, y, z in mesh.vertices]
    return MeshData(verts, mesh.elements, mesh.boundary)


def translate_mesh(mesh: MeshData, offset: tuple[float, float, float]) -> MeshData:
    ox, oy, oz = offset
    verts = [(x + ox, y + oy, z + oz) for x, y, z in mesh.vertices]
    return MeshData(verts, mesh.elements, mesh.boundary)


def permute_coordinate_axes(mesh: MeshData, axis_perm: Sequence[int]) -> MeshData:
    if sorted(axis_perm) != [0, 1, 2]:
        raise ValueError("axis_perm must permute axes 0,1,2")
    verts = []
    for x, y, z in mesh.vertices:
        coords = [x, y, z]
        verts.append((coords[axis_perm[0]], coords[axis_perm[1]], coords[axis_perm[2]]))
    return MeshData(verts, mesh.elements, mesh.boundary)


def reorder_boundary_faces(mesh: MeshData, order: Sequence[int]) -> MeshData:
    if len(order) != len(mesh.boundary):
        raise ValueError("order must permute every boundary face")
    boundary = [mesh.boundary[i] for i in order]
    return MeshData(mesh.vertices, mesh.elements, boundary)


def reverse_boundary_winding(mesh: MeshData, face_ids: Sequence[int]) -> MeshData:
    boundary = list(mesh.boundary)
    for fid in face_ids:
        v0, v1, v2, tag = boundary[fid]
        boundary[fid] = (v0, v2, v1, tag)
    return MeshData(mesh.vertices, mesh.elements, boundary)


def combined_transform(
    mesh: MeshData,
    *,
    vertex_perm: Sequence[int] | None = None,
    element_order: Sequence[int] | None = None,
    local_seed: int | None = None,
    boundary_order: Sequence[int] | None = None,
    reverse_faces: Sequence[int] | None = None,
) -> MeshData:
    out = mesh
    if vertex_perm is not None:
        out = permute_corner_vertices(out, vertex_perm)
    if element_order is not None:
        out = reorder_elements(out, element_order)
    if local_seed is not None:
        out = mixed_local_permutations(out, local_seed)
    if boundary_order is not None:
        out = reorder_boundary_faces(out, boundary_order)
    if reverse_faces is not None:
        out = reverse_boundary_winding(out, reverse_faces)
    return out


def invalid_mesh_nonfinite_coordinate() -> MeshData:
    mesh = unit_cube_mesh()
    verts = list(mesh.vertices)
    verts[0] = (float("nan"), 0.0, 0.0)
    return MeshData(verts, mesh.elements, mesh.boundary)


def invalid_mesh_unsupported_boundary_tag() -> MeshData:
    mesh = unit_cube_mesh()
    boundary = list(mesh.boundary)
    v0, v1, v2, _ = boundary[0]
    boundary[0] = (v0, v1, v2, "abc")
    return MeshData(mesh.vertices, mesh.elements, boundary)


def skewed_parallelepiped_mesh() -> MeshData:
    """Deterministic skewed cavity with the same topology as the unit cube."""
    base = unit_cube_mesh()
    verts = [(x + 0.35 * z, y + 0.2 * x, z) for x, y, z in base.vertices]
    return MeshData(verts, base.elements, base.boundary)


def two_cell_rectangular_cavity_mesh() -> MeshData:
    """2x1x1 rectangular cavity with the standard 12-tet center split."""
    base = unit_cube_mesh()
    verts = [(2.0 * x, y, z) for x, y, z in base.vertices]
    return MeshData(verts, base.elements, base.boundary)


def near_degenerate_valid_cavity_mesh() -> MeshData:
    """Thin but valid cavity with positive tet volumes."""
    base = unit_cube_mesh()
    verts = [(x, y, 5e-4 * z + 1e-6) for x, y, z in base.vertices]
    return MeshData(verts, base.elements, base.boundary)


def duplicate_coordinate_mesh() -> MeshData:
    """Distinct vertex ids that share identical coordinates."""
    base = unit_cube_mesh()
    verts = list(base.vertices)
    verts[1] = verts[0]
    return MeshData(verts, base.elements, base.boundary)


def boundary_face_not_on_tetra_mesh() -> MeshData:
    """PEC face on valid vertices that is not a face of any tetrahedron."""
    base = unit_cube_mesh()
    boundary = list(base.boundary)
    boundary[0] = (0, 2, 5, "pec")
    return MeshData(base.vertices, base.elements, boundary)
