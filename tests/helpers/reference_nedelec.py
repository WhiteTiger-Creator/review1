"""Independent NumPy/SciPy reference solver for the Maxwell cavity task.

This module is a **verifier-only** ground-truth implementation of a
first-order (lowest-order) Nedelec edge-element eigensolver for a closed,
perfectly-conducting (PEC) tetrahedral cavity. It is written from first
principles against the public mesh format and topology contract only -- it
never imports, links against, or shells out to the candidate C++ solver
(`/app/bin/emsolve` / `/app/emsolve`). It exists purely so the verifier can
compute an authoritative answer (eigenvalues, eigenvectors, operators,
residuals) and compare the candidate's reported output against it.

Public contract implemented here (mirrors ``instruction.md``):

* Mesh format: ``emsolve-mesh 1`` text format with ``vertices``,
  ``elements`` and ``boundary`` sections (see :func:`parse_mesh_text`).
* Canonical geometric edge enumeration: an edge is identified by its two
  endpoint *coordinates*, sorted lexicographically by ``(x, y, z)`` -- not
  by the (mesh-file-specific) vertex indices. Edges are that means the
  induced global edge ordering is invariant to vertex renumbering. Active
  (non-PEC) edges are sorted lexicographically by this same key, and each
  local occurrence of an edge inside a tetrahedron carries an orientation
  sign relative to the canonical (coordinate-sorted) endpoint order.
* First-order tetrahedral Nedelec (Whitney edge) elements assembled from
  barycentric gradients, with the curl-curl stiffness matrix ``K`` and mass
  matrix ``M`` built per-tet and scattered into global sparse operators
  using the canonical topology's DOF map and orientation signs.
* A generalized eigenproblem ``K x = lambda M x`` solved with
  ``scipy.sparse.linalg.eigsh`` for the lowest positive (physical) modes,
  skipping the spurious zero-eigenvalue gradient subspace.
* Independent residual diagnostics: algebraic generalized-eigenproblem
  residual, discrete divergence-free residual (via the vertex-edge
  gradient incidence operator), boundary trace residual, and mass-matrix
  orthonormality.
* Utilities to compare/derive modes across differently-numbered meshes via
  canonical edge keys, cluster near-degenerate eigenvalues, and compare
  eigenspaces via principal angles.

Only ``numpy`` and ``scipy.sparse`` (plus ``scipy.sparse.linalg`` and
``scipy.linalg``) are used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import linalg as dense_linalg
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import eigsh

# ---------------------------------------------------------------------------
# Tolerances (mirrors instruction.md / task.toml public contract).
# ---------------------------------------------------------------------------

BOUNDARY_TOL = 1e-8
DIVERGENCE_TOL = 1e-7
ALGEBRAIC_TOL = 1e-6
CLUSTER_REL_GAP_TOL = 1e-7

# Local (tet-relative) edge vertex pairs, in the same order used throughout
# the C++ contract: (0,1) (0,2) (0,3) (1,2) (1,3) (2,3).
LOCAL_EDGES: tuple[tuple[int, int], ...] = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedMesh:
    """In-memory representation of an ``emsolve-mesh 1`` file."""

    vertices: np.ndarray  # (nv, 3) float64
    elements: np.ndarray  # (nt, 4) int64 (vertex ids per tet)
    boundary: list[tuple[int, int, int, str]]
    source_path: str | None = None

    @property
    def num_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def num_elements(self) -> int:
        return int(self.elements.shape[0])


@dataclass
class CanonicalTopology:
    """Geometry-canonical edge topology, independent of vertex numbering."""

    edge_keys: list[tuple[tuple[float, float, float], tuple[float, float, float]]]
    edge_vertex_ids: list[tuple[int, int]]  # canonical (v0, v1) global vertex ids per gid
    elem_edge_global: np.ndarray  # (nt, 6) int -> global edge id
    elem_edge_sign: np.ndarray  # (nt, 6) int in {-1, +1}
    boundary_edges: frozenset[int]
    num_global_edges: int
    num_active_dofs: int
    reduced_to_global: list[int]  # active dofs sorted ascending by global id (== lexicographic)
    global_to_reduced: list[int]  # -1 for eliminated (PEC boundary) edges
    free_vertex_ids: list[int] = field(default_factory=list)  # non-PEC-boundary vertices


@dataclass
class OperatorPair:
    """Assembled global curl-curl (K) and mass (M) operators."""

    K: csr_matrix
    M: csr_matrix
    ndof: int


@dataclass
class PhysicalModes:
    """Lowest positive (physical) modes plus independent diagnostics."""

    eigenvalues: np.ndarray  # (nm,)
    coefficients: np.ndarray  # (ndof, nm), columns are eigenvectors
    cluster_ids: list[int]
    algebraic_residuals: np.ndarray
    divergence_residuals: np.ndarray
    boundary_trace_residuals: np.ndarray


# ---------------------------------------------------------------------------
# 1. Mesh parsing
# ---------------------------------------------------------------------------


def parse_mesh_text(text: str, source_path: str | None = None) -> ParsedMesh:
    """Parse an ``emsolve-mesh 1`` document from a string."""

    tokens = text.split()
    pos = 0

    def nxt() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("unexpected end of mesh text")
        tok = tokens[pos]
        pos += 1
        return tok

    header = nxt()
    if header != "emsolve-mesh":
        raise ValueError(f"invalid mesh header: {header!r}")
    version = int(nxt())
    if version != 1:
        raise ValueError(f"unsupported mesh version: {version}")

    tag = nxt()
    if tag != "vertices":
        raise ValueError("invalid vertices section")
    nverts = int(nxt())
    if nverts < 4:
        raise ValueError("invalid vertices section: too few vertices")
    vertices = np.zeros((nverts, 3), dtype=np.float64)
    for _ in range(nverts):
        vid = int(nxt())
        x = float(nxt())
        y = float(nxt())
        z = float(nxt())
        if not (0 <= vid < nverts):
            raise ValueError("vertex id out of range")
        vertices[vid] = (x, y, z)

    tag = nxt()
    if tag != "elements":
        raise ValueError("invalid elements section")
    ntets = int(nxt())
    if ntets < 1:
        raise ValueError("invalid elements section: no elements")
    elements = np.zeros((ntets, 4), dtype=np.int64)
    for _ in range(ntets):
        eid = int(nxt())
        vs = [int(nxt()) for _ in range(4)]
        if not (0 <= eid < ntets):
            raise ValueError("element id out of range")
        elements[eid] = vs

    tag = nxt()
    if tag != "boundary":
        raise ValueError("invalid boundary section")
    nfaces = int(nxt())
    boundary: list[tuple[int, int, int, str] | None] = [None] * nfaces
    for _ in range(nfaces):
        fid = int(nxt())
        a = int(nxt())
        b = int(nxt())
        c = int(nxt())
        face_tag = nxt()
        if not (0 <= fid < nfaces):
            raise ValueError("boundary id out of range")
        boundary[fid] = (a, b, c, face_tag)

    return ParsedMesh(
        vertices=vertices,
        elements=elements,
        boundary=[b for b in boundary if b is not None],
        source_path=source_path,
    )


def parse_mesh_file(path: str | Path) -> ParsedMesh:
    """Parse an ``emsolve-mesh 1`` file from disk."""

    p = Path(path)
    return parse_mesh_text(p.read_text(encoding="utf-8"), source_path=str(p))


def _coerce_mesh(mesh: ParsedMesh | str | Path | Any) -> ParsedMesh:
    """Accept a path, a :class:`ParsedMesh`, or a ``MeshData``-like object."""

    if isinstance(mesh, ParsedMesh):
        return mesh
    if isinstance(mesh, (str, Path)):
        return parse_mesh_file(mesh)
    # Duck-type a MeshData-like object (see tests/helpers/mesh_factory.py):
    # attributes `vertices`, `elements`, `boundary`.
    if hasattr(mesh, "vertices") and hasattr(mesh, "elements") and hasattr(mesh, "boundary"):
        vertices = np.asarray(list(mesh.vertices), dtype=np.float64)
        elements = np.asarray(list(mesh.elements), dtype=np.int64)
        boundary = [(int(a), int(b), int(c), str(tag)) for a, b, c, tag in mesh.boundary]
        return ParsedMesh(vertices=vertices, elements=elements, boundary=boundary)
    raise TypeError(f"cannot coerce object of type {type(mesh)!r} into a mesh")


# ---------------------------------------------------------------------------
# 2. Canonical geometric edge enumeration + topology (PEC elimination)
# ---------------------------------------------------------------------------


def _point_tuple(p: np.ndarray) -> tuple[float, float, float]:
    return (float(p[0]), float(p[1]), float(p[2]))


def _canonical_edge_key(
    pa: tuple[float, float, float], pb: tuple[float, float, float]
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Coordinate-sorted (lexicographic by x, y, z) endpoint pair."""

    if pb < pa:
        return (pb, pa)
    return (pa, pb)


def build_canonical_topology(mesh: ParsedMesh) -> CanonicalTopology:
    """Build a geometry-canonical edge topology with PEC elimination.

    Edges are identified purely by their endpoint *coordinates* (sorted
    lexicographically), so the resulting global edge ordering -- and hence
    the reduced (active) DOF ordering -- is invariant under vertex
    renumbering, element reordering, and local tetrahedron orientation
    flips of a geometrically identical mesh.
    """

    coords = [_point_tuple(mesh.vertices[i]) for i in range(mesh.num_vertices)]

    # Discover every geometric edge that appears either as a tet edge or as
    # a boundary-face edge (boundary edges are always a subset of tet edges,
    # but we register them defensively for robustness).
    key_to_gid: dict[tuple, int] = {}
    key_to_vertex_pair: dict[tuple, tuple[int, int]] = {}

    def register(a: int, b: int) -> None:
        key = _canonical_edge_key(coords[a], coords[b])
        if key not in key_to_vertex_pair:
            v0, v1 = (a, b) if key == (coords[a], coords[b]) else (b, a)
            key_to_vertex_pair[key] = (v0, v1)

    for tet in mesh.elements:
        for i, j in LOCAL_EDGES:
            register(int(tet[i]), int(tet[j]))
    for a, b, c, tag in mesh.boundary:
        if tag != "pec":
            continue
        register(a, b)
        register(b, c)
        register(a, c)

    sorted_keys = sorted(key_to_vertex_pair.keys())
    for gid, key in enumerate(sorted_keys):
        key_to_gid[key] = gid

    num_global_edges = len(sorted_keys)
    edge_keys = list(sorted_keys)
    edge_vertex_ids = [key_to_vertex_pair[k] for k in sorted_keys]

    def edge_gid(a: int, b: int) -> int:
        return key_to_gid[_canonical_edge_key(coords[a], coords[b])]

    ntets = mesh.num_elements
    elem_edge_global = np.zeros((ntets, 6), dtype=np.int64)
    elem_edge_sign = np.zeros((ntets, 6), dtype=np.int64)
    for e, tet in enumerate(mesh.elements):
        for le, (i, j) in enumerate(LOCAL_EDGES):
            ga, gb = int(tet[i]), int(tet[j])
            gid = edge_gid(ga, gb)
            elem_edge_global[e, le] = gid
            v0, v1 = edge_vertex_ids[gid]
            elem_edge_sign[e, le] = 1 if (ga, gb) == (v0, v1) else -1

    boundary_edge_set: set[int] = set()
    boundary_vertex_set: set[int] = set()
    for a, b, c, tag in mesh.boundary:
        if tag != "pec":
            continue
        boundary_edge_set.add(edge_gid(a, b))
        boundary_edge_set.add(edge_gid(b, c))
        boundary_edge_set.add(edge_gid(a, c))
        boundary_vertex_set.update((a, b, c))

    active = sorted(gid for gid in range(num_global_edges) if gid not in boundary_edge_set)
    num_active_dofs = len(active)
    global_to_reduced = [-1] * num_global_edges
    for r, gid in enumerate(active):
        global_to_reduced[gid] = r

    free_vertex_ids = sorted(v for v in range(mesh.num_vertices) if v not in boundary_vertex_set)

    return CanonicalTopology(
        edge_keys=edge_keys,
        edge_vertex_ids=edge_vertex_ids,
        elem_edge_global=elem_edge_global,
        elem_edge_sign=elem_edge_sign,
        boundary_edges=frozenset(boundary_edge_set),
        num_global_edges=num_global_edges,
        num_active_dofs=num_active_dofs,
        reduced_to_global=active,
        global_to_reduced=global_to_reduced,
        free_vertex_ids=free_vertex_ids,
    )


# ---------------------------------------------------------------------------
# 3/4. First-order Nedelec local element matrices
# ---------------------------------------------------------------------------

# 4-point tetrahedral quadrature exact for polynomials up to degree 2
# (Keast/Zienkiewicz rule), given as barycentric-coordinate points with
# equal weight 1/4 each (weights sum to 1; multiply by the tet volume for
# the physical quadrature weight). The Nedelec mass-matrix integrand
# (N_i . N_j) is exactly quadratic in barycentric coordinates, so this rule
# integrates it exactly.
_QUAD_ALPHA = (5.0 + 3.0 * math.sqrt(5.0)) / 20.0
_QUAD_BETA = (5.0 - math.sqrt(5.0)) / 20.0
QUADRATURE_POINTS: np.ndarray = np.array(
    [
        [_QUAD_ALPHA, _QUAD_BETA, _QUAD_BETA, _QUAD_BETA],
        [_QUAD_BETA, _QUAD_ALPHA, _QUAD_BETA, _QUAD_BETA],
        [_QUAD_BETA, _QUAD_BETA, _QUAD_ALPHA, _QUAD_BETA],
        [_QUAD_BETA, _QUAD_BETA, _QUAD_BETA, _QUAD_ALPHA],
    ]
)
QUADRATURE_WEIGHTS: np.ndarray = np.full(4, 0.25)


def barycentric_gradients(pts: np.ndarray) -> tuple[np.ndarray, float]:
    """Return the four constant barycentric gradients and the tet volume.

    ``pts`` is a ``(4, 3)`` array of vertex coordinates ``p0..p3``. Uses
    ``lambda_1..lambda_3 = Minv @ (p - p0)`` where ``M`` has the tet edge
    vectors from ``p0`` as columns, so ``grad(lambda_k)`` is the k-th row
    of ``Minv`` (k=1..3), and ``grad(lambda_0) = -sum(grad(lambda_{1..3}))``
    since the barycentric coordinates sum to 1 everywhere.
    """

    p0, p1, p2, p3 = pts[0], pts[1], pts[2], pts[3]
    mat = np.column_stack((p1 - p0, p2 - p0, p3 - p0))
    det = np.linalg.det(mat)
    volume = abs(det) / 6.0
    if volume <= 1e-14:
        raise ValueError("degenerate tetrahedron")
    minv = np.linalg.inv(mat)
    grad1 = minv[0, :]
    grad2 = minv[1, :]
    grad3 = minv[2, :]
    grad0 = -(grad1 + grad2 + grad3)
    grads = np.vstack((grad0, grad1, grad2, grad3))
    return grads, volume


def local_nedelec_matrices(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Assemble the 6x6 local curl-curl (K) and mass (M) matrices.

    Edge basis: ``N_ij = lambda_i * grad(lambda_j) - lambda_j * grad(lambda_i)``.
    ``curl(N_ij) = 2 * cross(grad(lambda_i), grad(lambda_j))`` (constant per tet).
    ``K_e[a, b] = V * curl_a . curl_b``.
    ``M_e[a, b] = integral_tet N_a . N_b dV`` via the 4-point quadrature above.

    Returns ``(Kloc, Mloc, curls, volume)``.
    """

    grads, volume = barycentric_gradients(pts)

    curls = np.zeros((6, 3), dtype=np.float64)
    for a, (i, j) in enumerate(LOCAL_EDGES):
        curls[a] = 2.0 * np.cross(grads[i], grads[j])

    kloc = volume * (curls @ curls.T)

    mloc = np.zeros((6, 6), dtype=np.float64)
    for q in range(QUADRATURE_POINTS.shape[0]):
        lam = QUADRATURE_POINTS[q]
        w = QUADRATURE_WEIGHTS[q] * volume
        basis = np.zeros((6, 3), dtype=np.float64)
        for a, (i, j) in enumerate(LOCAL_EDGES):
            basis[a] = lam[i] * grads[j] - lam[j] * grads[i]
        mloc += w * (basis @ basis.T)

    return kloc, mloc, curls, volume


# ---------------------------------------------------------------------------
# 5. Global sparse assembly
# ---------------------------------------------------------------------------


def assemble_global_operators(mesh: ParsedMesh, topo: CanonicalTopology) -> OperatorPair:
    """Assemble global K, M sparse operators with orientation signs applied."""

    ndof = topo.num_active_dofs
    k_mat = lil_matrix((ndof, ndof), dtype=np.float64)
    m_mat = lil_matrix((ndof, ndof), dtype=np.float64)

    for e in range(mesh.num_elements):
        tet = mesh.elements[e]
        pts = mesh.vertices[tet]
        kloc, mloc, _curls, _vol = local_nedelec_matrices(pts)

        gids = topo.elem_edge_global[e]
        signs = topo.elem_edge_sign[e]
        reduced = [topo.global_to_reduced[int(g)] for g in gids]

        for a in range(6):
            ra = reduced[a]
            if ra < 0:
                continue
            for b in range(6):
                rb = reduced[b]
                if rb < 0:
                    continue
                s = float(signs[a] * signs[b])
                k_mat[ra, rb] += s * kloc[a, b]
                m_mat[ra, rb] += s * mloc[a, b]

    return OperatorPair(K=k_mat.tocsr(), M=m_mat.tocsr(), ndof=ndof)


# ---------------------------------------------------------------------------
# 6. Generalized eigenproblem: lowest positive (physical) modes
# ---------------------------------------------------------------------------


def solve_lowest_physical_modes(
    K: csr_matrix,
    M: csr_matrix,
    n_modes: int,
    *,
    null_space_hint: int = 0,
    zero_tol: float = 1e-8,
    sigma: float = -1.0e-2,
) -> tuple[np.ndarray, np.ndarray]:
    """Solve ``K x = lambda M x`` for the lowest ``n_modes`` positive eigenpairs.

    The lowest-order Nedelec discretization of a closed PEC cavity has an
    exact-zero-eigenvalue subspace spanned by gradients of the interior
    (non-boundary) nodal basis functions (since ``curl(grad phi) = 0``).
    These are spurious static modes and are filtered out; only physical
    (strictly positive) eigenvalues are returned, sorted ascending.

    Uses ``scipy.sparse.linalg.eigsh`` in shift-invert mode with a small
    negative shift ``sigma`` (valid since ``K`` is PSD and ``M`` is SPD, so
    ``K - sigma * M`` stays nonsingular and well conditioned) to reliably
    resolve the lowest part of the spectrum, including the exact zeros.
    """

    ndof = K.shape[0]
    if ndof < 2:
        raise ValueError("too few active degrees of freedom to solve eigenproblem")

    k_req = min(ndof - 1, max(n_modes + null_space_hint + 2, n_modes + 1))
    k_req = max(k_req, 1)

    vals, vecs = eigsh(K, k=k_req, M=M, sigma=sigma, which="LM")
    order = np.argsort(vals)
    vals = vals[order]
    vecs = vecs[:, order]

    scale = max(1.0, float(np.max(np.abs(vals))) if vals.size else 1.0)
    physical_mask = vals > zero_tol * scale
    phys_vals = vals[physical_mask]
    phys_vecs = vecs[:, physical_mask]

    if phys_vals.size < n_modes:
        # Retry with a larger subspace before giving up, in case the initial
        # guess for the null-space dimension undershot.
        k_req2 = min(ndof - 1, k_req + n_modes + 4)
        if k_req2 > k_req:
            vals, vecs = eigsh(K, k=k_req2, M=M, sigma=sigma, which="LM")
            order = np.argsort(vals)
            vals = vals[order]
            vecs = vecs[:, order]
            scale = max(1.0, float(np.max(np.abs(vals))) if vals.size else 1.0)
            physical_mask = vals > zero_tol * scale
            phys_vals = vals[physical_mask]
            phys_vecs = vecs[:, physical_mask]

    if phys_vals.size < n_modes:
        raise RuntimeError(
            f"could not resolve {n_modes} physical modes "
            f"(found {phys_vals.size} of {k_req2 if 'k_req2' in dir() else k_req} computed)"
        )

    return phys_vals[:n_modes], phys_vecs[:, :n_modes]


# ---------------------------------------------------------------------------
# 7. Discrete divergence residual via vertex-edge incidence
# ---------------------------------------------------------------------------


def build_gradient_incidence(mesh: ParsedMesh, topo: CanonicalTopology) -> csr_matrix:
    """Discrete gradient (vertex -> active-edge) incidence operator.

    Row ``r`` (an active/reduced edge dof with canonical endpoints
    ``(v0, v1)``) has a ``-1`` in the column for free vertex ``v0`` and a
    ``+1`` in the column for free vertex ``v1`` (PEC boundary vertices are
    Dirichlet-eliminated and contribute no column). For any scalar nodal
    function ``phi`` on the free vertices, ``G @ phi`` reproduces the edge
    DOFs of ``grad(phi)`` in the Nedelec basis: a genuinely curl-free field
    that a divergence-free (transverse) physical eigenmode must be
    ``M``-orthogonal to.
    """

    free_index = {v: i for i, v in enumerate(topo.free_vertex_ids)}
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for gid in range(topo.num_global_edges):
        r = topo.global_to_reduced[gid]
        if r < 0:
            continue
        v0, v1 = topo.edge_vertex_ids[gid]
        if v0 in free_index:
            rows.append(r)
            cols.append(free_index[v0])
            data.append(-1.0)
        if v1 in free_index:
            rows.append(r)
            cols.append(free_index[v1])
            data.append(1.0)
    shape = (topo.num_active_dofs, len(topo.free_vertex_ids))
    return csr_matrix((data, (rows, cols)), shape=shape)


def recompute_divergence_residuals(
    mesh: ParsedMesh | Any,
    topo: CanonicalTopology,
    vectors: Sequence[np.ndarray] | np.ndarray,
    M: csr_matrix | None = None,
) -> np.ndarray:
    """Discrete divergence-free residual for each mode's active-DOF vector.

    residual_k = ||G^T (M x_k)|| / max(1, ||M x_k||)

    where ``G`` is the vertex-edge gradient incidence operator restricted to
    active edges and free (non-PEC) vertices. A genuine physical mode is
    ``M``-orthogonal to every discrete gradient field, so this residual
    should be at/near machine precision (well within ``DIVERGENCE_TOL``).
    """

    mesh = _coerce_mesh(mesh)
    G = build_gradient_incidence(mesh, topo)

    if M is None:
        ops = assemble_global_operators(mesh, topo)
        M = ops.M

    vecs = np.asarray(vectors, dtype=np.float64)
    if vecs.ndim == 1:
        vecs = vecs.reshape(-1, 1)
    elif vecs.shape[0] != topo.num_active_dofs and vecs.shape[1] == topo.num_active_dofs:
        vecs = vecs.T

    residuals = np.zeros(vecs.shape[1], dtype=np.float64)
    for k in range(vecs.shape[1]):
        x = vecs[:, k]
        mx = M @ x
        proj = G.T @ mx
        denom = max(1.0, float(np.linalg.norm(mx)))
        residuals[k] = float(np.linalg.norm(proj)) / denom
    return residuals


# ---------------------------------------------------------------------------
# 8. Algebraic residual, boundary trace residual, mass orthonormality
# ---------------------------------------------------------------------------


def recompute_algebraic_residuals(
    K: csr_matrix,
    M: csr_matrix,
    lambdas: Sequence[float] | np.ndarray,
    vectors: Sequence[np.ndarray] | np.ndarray,
) -> np.ndarray:
    """``||K x - lambda * M x|| / max(1, ||x||)`` for each (lambda, x) pair."""

    lambdas = np.asarray(lambdas, dtype=np.float64)
    vecs = np.asarray(vectors, dtype=np.float64)
    if vecs.ndim == 1:
        vecs = vecs.reshape(-1, 1)
    elif vecs.shape[0] != K.shape[0] and vecs.shape[1] == K.shape[0]:
        vecs = vecs.T

    residuals = np.zeros(len(lambdas), dtype=np.float64)
    for i, lam in enumerate(lambdas):
        x = vecs[:, i]
        r = K @ x - lam * (M @ x)
        residuals[i] = float(np.linalg.norm(r)) / max(1.0, float(np.linalg.norm(x)))
    return residuals


def boundary_trace_residual(
    mesh: ParsedMesh | Any,
    topo: CanonicalTopology,
    x_reduced: np.ndarray,
) -> float:
    """RMS tangential trace on eliminated (PEC) boundary edges.

    Since PEC boundary edges are removed from the active DOF set by
    construction, the trace is reconstructed by expanding any candidate
    full-edge field (mapped through :func:`map_coefficients_between_topologies`
    or an equivalent geometric mapping) back to this topology's global edge
    numbering and reading off the boundary components; for a vector that
    only ever lives in the (already boundary-eliminated) reduced space, the
    residual is identically zero by construction.
    """

    del mesh  # geometry is only needed by callers building a full-edge field
    if not topo.boundary_edges:
        return 0.0
    # x_reduced lives purely on active edges: boundary contribution is 0.
    del x_reduced
    return 0.0


def mass_orthonormality_residual(M: csr_matrix, vectors: np.ndarray) -> np.ndarray:
    """``|| V^T M V - I ||`` style pairwise residual matrix for a mode block."""

    vecs = np.asarray(vectors, dtype=np.float64)
    if vecs.ndim == 1:
        vecs = vecs.reshape(-1, 1)
    gram = vecs.T @ (M @ vecs)
    return gram - np.eye(gram.shape[0])


# ---------------------------------------------------------------------------
# 9. Mapping modes between meshes via canonical edge keys
# ---------------------------------------------------------------------------


def map_coefficients_between_topologies(
    topo_a: CanonicalTopology,
    topo_b: CanonicalTopology,
    coeffs: np.ndarray,
    *,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Remap a reduced-DOF coefficient vector from ``topo_a`` to ``topo_b``.

    Both topologies are canonicalized purely from vertex *coordinates*, so
    for geometrically identical meshes the active-edge orderings coincide
    exactly and no sign flip is required for the remap (canonical
    orientation only depends on geometry, never on vertex numbering).
    Coefficients for edges missing in ``topo_b`` (e.g. differing PEC
    tagging) are filled with ``fill_value``.
    """

    coeffs = np.asarray(coeffs, dtype=np.float64)
    is_1d = coeffs.ndim == 1
    if is_1d:
        coeffs = coeffs.reshape(-1, 1)

    key_to_gid_b = {key: gid for gid, key in enumerate(topo_b.edge_keys)}

    out = np.full((topo_b.num_active_dofs, coeffs.shape[1]), fill_value, dtype=np.float64)
    for r_a, gid_a in enumerate(topo_a.reduced_to_global):
        key = topo_a.edge_keys[gid_a]
        gid_b = key_to_gid_b.get(key)
        if gid_b is None:
            continue
        r_b = topo_b.global_to_reduced[gid_b]
        if r_b < 0:
            continue
        out[r_b, :] = coeffs[r_a, :]

    return out[:, 0] if is_1d else out


# ---------------------------------------------------------------------------
# 10. Eigenvalue clustering (relative-gap rule)
# ---------------------------------------------------------------------------


def cluster_eigenvalues(values: Sequence[float], tol: float = CLUSTER_REL_GAP_TOL) -> list[list[int]]:
    """Group (near-)degenerate eigenvalues using a *relative* gap rule.

    Two consecutive (sorted) eigenvalues belong to the same cluster when
    ``|v_i - v_{i-1}| / max(|v_i|, |v_{i-1}|, 1.0) <= tol``. Returns a list
    of clusters, each a list of original indices into ``values``.
    """

    idx = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[list[int]] = []
    cur: list[int] = []
    prev = None
    for i in idx:
        v = values[i]
        if prev is None:
            cur = [i]
        else:
            denom = max(abs(v), abs(prev), 1.0)
            rel_gap = abs(v - prev) / denom
            if rel_gap <= tol:
                cur.append(i)
            else:
                clusters.append(cur)
                cur = [i]
        prev = v
    if cur:
        clusters.append(cur)
    return clusters


# ---------------------------------------------------------------------------
# 11. Principal angles for subspace comparison
# ---------------------------------------------------------------------------


def principal_angles(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Principal angles (radians) between the column spaces of A and B."""

    qa, _ = np.linalg.qr(np.asarray(A, dtype=np.float64))
    qb, _ = np.linalg.qr(np.asarray(B, dtype=np.float64))
    s = np.linalg.svd(qa.T @ qb, compute_uv=False)
    s = np.clip(s, -1.0, 1.0)
    return np.arccos(s)


def subspace_equivalent(A: np.ndarray, B: np.ndarray, angle_tol: float = 0.08) -> bool:
    if A.shape != B.shape:
        return False
    angles = principal_angles(A, B)
    return bool(np.all(angles <= angle_tol))


# ---------------------------------------------------------------------------
# Operator property verification
# ---------------------------------------------------------------------------


def verify_operator_properties(
    K: csr_matrix, M: csr_matrix, *, psd_tol: float = 1e-9, pd_tol: float = 1e-12
) -> dict[str, Any]:
    """Check that ``K`` is symmetric PSD and ``M`` is symmetric PD.

    For the small dense operators produced by verifier-generated cavity
    meshes, extreme eigenvalues are computed directly with a dense
    symmetric eigensolver (robust for tiny matrices, where sparse ARPACK
    routines are awkward/ill-posed).
    """

    k_dense = K.toarray() if hasattr(K, "toarray") else np.asarray(K)
    m_dense = M.toarray() if hasattr(M, "toarray") else np.asarray(M)

    k_sym_err = float(np.max(np.abs(k_dense - k_dense.T))) if k_dense.size else 0.0
    m_sym_err = float(np.max(np.abs(m_dense - m_dense.T))) if m_dense.size else 0.0

    k_eigvals = dense_linalg.eigh(k_dense, eigvals_only=True) if k_dense.size else np.array([0.0])
    m_eigvals = dense_linalg.eigh(m_dense, eigvals_only=True) if m_dense.size else np.array([0.0])

    k_min = float(np.min(k_eigvals))
    m_min = float(np.min(m_eigvals))

    return {
        "k_symmetric": k_sym_err <= 1e-8 * max(1.0, float(np.max(np.abs(k_dense)) if k_dense.size else 1.0)),
        "m_symmetric": m_sym_err <= 1e-8 * max(1.0, float(np.max(np.abs(m_dense)) if m_dense.size else 1.0)),
        "k_min_eigenvalue": k_min,
        "m_min_eigenvalue": m_min,
        "k_is_psd": k_min >= -psd_tol * max(1.0, float(np.max(np.abs(k_eigvals)))),
        "m_is_pd": m_min > pd_tol * max(1.0, float(np.max(np.abs(m_eigvals)))),
    }


# ---------------------------------------------------------------------------
# Scale-law check
# ---------------------------------------------------------------------------


def scale_law_check(
    base_mesh: ParsedMesh | Any,
    scaled_mesh: ParsedMesh | Any,
    scale: float | tuple[float, float, float],
    modes_base: Mapping[str, Any],
    modes_scaled: Mapping[str, Any],
    *,
    rtol: float = 1e-4,
) -> dict[str, Any]:
    """Check the ``lambda -> lambda / scale^2`` isotropic-scaling law.

    Under a uniform positive geometric scaling of the cavity by factor
    ``s`` (``coords -> s * coords``), the curl-curl stiffness scales as
    ``1/s`` and the mass matrix scales as ``s``, so each Maxwell eigenvalue
    scales as ``1/s**2``. ``base_mesh``/``scaled_mesh`` are accepted for
    interface symmetry with the rest of this module (and to allow future
    geometric sanity checks); the numeric law is verified on the
    eigenvalues in ``modes_base``/``modes_scaled`` (as produced by
    :func:`build_reference_solution`).
    """

    _coerce_mesh(base_mesh)
    _coerce_mesh(scaled_mesh)

    if isinstance(scale, (tuple, list)):
        values = [float(s) for s in scale]
        if max(values) - min(values) > 1e-12 * max(1.0, max(abs(v) for v in values)):
            raise NotImplementedError(
                "scale_law_check only supports isotropic (uniform) scale factors"
            )
        s = values[0]
    else:
        s = float(scale)

    lam_base = np.asarray(modes_base["eigenvalues"], dtype=np.float64)
    lam_scaled = np.asarray(modes_scaled["eigenvalues"], dtype=np.float64)
    n = min(lam_base.size, lam_scaled.size)
    lam_base = lam_base[:n]
    lam_scaled = lam_scaled[:n]

    predicted = lam_base / (s ** 2)
    denom = np.maximum(np.abs(predicted), 1.0)
    rel_err = np.abs(lam_scaled - predicted) / denom

    return {
        "scale": s,
        "predicted": predicted.tolist(),
        "actual": lam_scaled.tolist(),
        "relative_errors": rel_err.tolist(),
        "max_relative_error": float(np.max(rel_err)) if rel_err.size else 0.0,
        "passed": bool(np.all(rel_err <= rtol)),
    }


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


def build_reference_solution(
    mesh: str | Path | ParsedMesh | Any,
    n_modes: int,
    *,
    cluster_tol: float = CLUSTER_REL_GAP_TOL,
) -> dict[str, Any]:
    """Compute the authoritative (independent) solution for ``mesh``.

    Parameters
    ----------
    mesh:
        A filesystem path to an ``emsolve-mesh 1`` file, a
        :class:`ParsedMesh`, or a ``MeshData``-like object (see
        ``tests/helpers/mesh_factory.py``) exposing ``vertices``,
        ``elements`` and ``boundary``.
    n_modes:
        Number of lowest positive physical modes to return.

    Returns
    -------
    dict with keys:
        ``eigenvalues``    -- (n_modes,) ndarray, ascending.
        ``coefficients``   -- (n_modes,) list of (ndof,) ndarrays.
        ``cluster_ids``    -- list[int], relative-gap clustering of eigenvalues.
        ``K``, ``M``       -- assembled sparse operators (active-DOF space).
        ``topology``       -- :class:`CanonicalTopology`.
        ``mesh``           -- the parsed :class:`ParsedMesh`.
        ``diagnostics``    -- dict with ``algebraic``, ``divergence``,
                               ``boundary_trace`` residual arrays and
                               ``operator_properties``.
    """

    parsed = _coerce_mesh(mesh)
    topo = build_canonical_topology(parsed)
    ops = assemble_global_operators(parsed, topo)

    null_hint = len(topo.free_vertex_ids)
    lambdas, vecs = solve_lowest_physical_modes(ops.K, ops.M, n_modes, null_space_hint=null_hint)

    alg_res = recompute_algebraic_residuals(ops.K, ops.M, lambdas, vecs)
    div_res = recompute_divergence_residuals(parsed, topo, vecs, M=ops.M)
    bnd_res = np.array(
        [boundary_trace_residual(parsed, topo, vecs[:, i]) for i in range(vecs.shape[1])]
    )

    clusters = cluster_eigenvalues(lambdas.tolist(), tol=cluster_tol)
    cluster_ids = [0] * len(lambdas)
    for cid, members in enumerate(clusters):
        for m in members:
            cluster_ids[m] = cid

    op_props = verify_operator_properties(ops.K, ops.M)

    return {
        "eigenvalues": lambdas,
        "coefficients": [vecs[:, i].copy() for i in range(vecs.shape[1])],
        "cluster_ids": cluster_ids,
        "K": ops.K,
        "M": ops.M,
        "topology": topo,
        "mesh": parsed,
        "diagnostics": {
            "algebraic": alg_res,
            "divergence": div_res,
            "boundary_trace": bnd_res,
            "operator_properties": op_props,
        },
    }


__all__ = [
    "ALGEBRAIC_TOL",
    "BOUNDARY_TOL",
    "CLUSTER_REL_GAP_TOL",
    "DIVERGENCE_TOL",
    "LOCAL_EDGES",
    "QUADRATURE_POINTS",
    "QUADRATURE_WEIGHTS",
    "CanonicalTopology",
    "OperatorPair",
    "ParsedMesh",
    "PhysicalModes",
    "assemble_global_operators",
    "barycentric_gradients",
    "boundary_trace_residual",
    "build_canonical_topology",
    "build_gradient_incidence",
    "build_reference_solution",
    "cluster_eigenvalues",
    "local_nedelec_matrices",
    "map_coefficients_between_topologies",
    "mass_orthonormality_residual",
    "parse_mesh_file",
    "parse_mesh_text",
    "principal_angles",
    "recompute_algebraic_residuals",
    "recompute_divergence_residuals",
    "scale_law_check",
    "solve_lowest_physical_modes",
    "subspace_equivalent",
    "verify_operator_properties",
]
