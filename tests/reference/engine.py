"""Full reconcile(data_dir) -> report dict implementing precedence, lock, and report rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reference.canonical import sha256_hex
from reference.loader import (
    MalformedJsonError,
    MissingRequiredInputError,
    load_data_dir,
)
from reference.versioning import (
    InvalidVersionError,
    candidate_matches,
    parse_version,
    source_version_matches,
)

SECTION_ORDER = {
    "declaration": 0,
    "provider": 1,
    "package_selection": 2,
    "target_graph": 3,
    "final_resolution": 4,
}

SECTION_NAMES = (
    "declaration",
    "provider",
    "package_selection",
    "target_graph",
    "final_resolution",
)


class WholeRunFatal(Exception):
    def __init__(self, reason_token: str) -> None:
        self.reason_token = reason_token
        super().__init__(reason_token)


def normalize_name(name: str) -> str:
    return name.strip().lower()


def sort_unique_components(components: list[str]) -> list[str]:
    return sorted(set(components))


def sort_unique_strings(values: list[str]) -> list[str]:
    return sorted(set(values))


@dataclass
class Resolution:
    source_kind: str
    identity_or_null: str | None
    version_or_null: str | None
    components: list[str]
    produced_targets: list[str]
    provider_response_id_or_null: str | None = None
    provider_satisfies_or_null: bool | None = None
    provider_intercepted: bool = False
    provider_outcome: str = "provider_skipped"
    version_failed: bool = False
    components_failed: bool = False


@dataclass
class ConfigureState:
    configure_request_id: str
    request_index: int
    project_id: str
    provider_config_id: str
    lock_mode: str
    previous_lock: dict[str, Any] | None
    find_requests: list[dict[str, Any]]
    resolutions: dict[str, Resolution] = field(default_factory=dict)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    provider_rows: list[dict[str, Any]] = field(default_factory=list)
    package_selection_rows: list[dict[str, Any]] = field(default_factory=list)
    target_rows: list[dict[str, Any]] = field(default_factory=list)
    lock_section_rows: list[dict[str, Any]] = field(default_factory=list)
    action: str = "reuse_resolution"
    resolved_dependency_count: int = 0
    reused_section_count: int = 0
    updated_section_count: int = 0
    rejected: bool = False


def _validate_version_or_null(value: str | None) -> None:
    if value is not None:
        parse_version(value)


def _components_satisfied(required: list[str], provided: list[str]) -> bool:
    provided_set = set(provided)
    return all(component in provided_set for component in required)


def _build_indexes(data: dict[str, Any]) -> dict[str, Any]:
    declarations = data["declarations"]
    find_requests = data["find_requests"]
    providers = {p["provider_config_id"]: p for p in data["providers"]}
    responses = data["provider_responses"]
    candidates = data["candidates"]
    overrides = data["overrides"]
    target_graph = data["target_graph"]
    locks = {lock["lock_id"]: lock for lock in data["locks"]}
    configure_requests = data["policy"]["configure_requests"]

    find_by_id = {row["find_request_id"]: row for row in find_requests}

    for decl in declarations:
        _validate_version_or_null(decl.get("declared_version_or_null"))
        fpa = decl["find_package_args"]
        _validate_version_or_null(fpa.get("version_or_null"))

    for row in find_requests:
        _validate_version_or_null(row.get("version_or_null"))

    for override in overrides:
        _validate_version_or_null(override.get("version_or_null"))

    for response in responses:
        _validate_version_or_null(response.get("version_or_null"))

    for candidate in candidates:
        parse_version(candidate["version"])

    seen_cfg_index: set[int] = set()
    for cfg in configure_requests:
        idx = cfg["request_index"]
        if idx in seen_cfg_index:
            raise WholeRunFatal("duplicate_configure_request_index")
        seen_cfg_index.add(idx)
        if cfg["provider_config_id"] not in providers:
            raise WholeRunFatal("unknown_reference")
        if cfg.get("previous_lock_id_or_null") is not None:
            if cfg["previous_lock_id_or_null"] not in locks:
                raise WholeRunFatal("unknown_reference")
        for find_id in cfg["find_request_ids"]:
            if find_id not in find_by_id:
                raise WholeRunFatal("unknown_reference")

    declarations_by_project: dict[str, list[dict[str, Any]]] = {}
    for decl in declarations:
        declarations_by_project.setdefault(decl["project_id"], []).append(decl)

    ownership_by_project: dict[str, dict[str, dict[str, Any]]] = {}
    shadowed_ids: set[str] = set()
    for project_id, decls in declarations_by_project.items():
        seen_index: set[int] = set()
        sorted_decls = sorted(
            decls,
            key=lambda d: (d["declaration_index"], d["declaration_id"]),
        )
        owners: dict[str, dict[str, Any]] = {}
        for decl in sorted_decls:
            if decl["declaration_index"] in seen_index:
                raise WholeRunFatal("duplicate_declaration_index")
            seen_index.add(decl["declaration_index"])
            norm = normalize_name(decl["dependency_name"])
            if norm in owners:
                shadowed_ids.add(decl["declaration_id"])
            else:
                owners[norm] = decl
                owner = owners[norm]
                if owner["override_find_package"] and owner["find_package_args"]["enabled"]:
                    raise WholeRunFatal("conflicting_declaration_flags")
        ownership_by_project[project_id] = owners

    find_by_project: dict[str, list[dict[str, Any]]] = {}
    for row in find_requests:
        find_by_project.setdefault(row["project_id"], []).append(row)
    for _project_id, rows in find_by_project.items():
        seen_index: set[int] = set()
        for row in rows:
            if row["request_index"] in seen_index:
                raise WholeRunFatal("duplicate_find_request_index")
            seen_index.add(row["request_index"])

    active_overrides: dict[str, dict[str, Any]] = {}
    for override in overrides:
        if not override.get("active"):
            continue
        norm = normalize_name(override["dependency_name"])
        if norm in active_overrides:
            raise WholeRunFatal("invalid_input_schema")
        active_overrides[norm] = override

    responses_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for response in responses:
        key = (
            response["provider_config_id"],
            normalize_name(response["dependency_name"]),
            response["request_kind"],
        )
        responses_by_key.setdefault(key, []).append(response)
    for key, items in responses_by_key.items():
        responses_by_key[key] = sorted(items, key=lambda r: r["response_id"])

    candidates_by_name: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        norm = normalize_name(candidate["dependency_name"])
        candidates_by_name.setdefault(norm, []).append(candidate)
    for norm, items in candidates_by_name.items():
        candidates_by_name[norm] = sorted(items, key=lambda c: c["candidate_id"])

    targets = {t["target_id"]: t for t in target_graph.get("targets", [])}
    edges = target_graph.get("edges", [])

    return {
        "declarations": declarations,
        "find_by_id": find_by_id,
        "providers": providers,
        "responses_by_key": responses_by_key,
        "candidates_by_name": candidates_by_name,
        "active_overrides": active_overrides,
        "targets": targets,
        "edges": edges,
        "locks": locks,
        "configure_requests": sorted(
            configure_requests, key=lambda c: c["request_index"]
        ),
        "ownership_by_project": ownership_by_project,
        "shadowed_ids": shadowed_ids,
    }


def _pick_provider_response(
    indexes: dict[str, Any],
    provider_config_id: str,
    dependency_name: str,
    request_kind: str,
) -> dict[str, Any] | None:
    key = (provider_config_id, normalize_name(dependency_name), request_kind)
    items = indexes["responses_by_key"].get(key, [])
    return items[0] if items else None


def _pick_package_candidate(
    indexes: dict[str, Any],
    dependency_name: str,
    request: dict[str, Any],
) -> dict[str, Any] | None:
    norm = normalize_name(dependency_name)
    components = sort_unique_components(request.get("components", []))
    for candidate in indexes["candidates_by_name"].get(norm, []):
        if not candidate_matches(
            candidate["version"],
            candidate["compatibility"],
            request.get("version_or_null"),
            request.get("exact", False),
        ):
            continue
        if not _components_satisfied(components, candidate.get("provided_components", [])):
            continue
        return candidate
    return None


def _fetchcontent_components_ok(request_components: list[str]) -> bool:
    if not request_components:
        return True
    allowed = {"default"}
    return set(request_components).issubset(allowed)


def _resolve_find_package(
    indexes: dict[str, Any],
    project_id: str,
    request: dict[str, Any],
    provider_config: dict[str, Any],
) -> Resolution:
    norm = normalize_name(request["dependency_name"])
    owner = indexes["ownership_by_project"].get(project_id, {}).get(norm)
    components = sort_unique_components(request.get("components", []))
    bypass = request.get("bypass_provider", False)
    override = indexes["active_overrides"].get(norm)

    version_failed = False
    components_failed = False

    if override is not None:
        if not source_version_matches(
            override.get("version_or_null"),
            request.get("version_or_null"),
            request.get("exact", False),
        ):
            version_failed = True
        elif not _components_satisfied(components, override.get("provided_components", [])):
            components_failed = True
        else:
            return Resolution(
                source_kind="override",
                identity_or_null=override["override_id"],
                version_or_null=override.get("version_or_null"),
                components=components,
                produced_targets=list(override.get("produced_targets", [])),
                provider_outcome="provider_skipped",
            )

    intercepted = False
    outcome = "provider_skipped"
    response_id_or_null: str | None = None
    satisfies_or_null: bool | None = None

    intercept = (
        not bypass
        and provider_config.get("intercept_find_package", False)
    )
    if intercept:
        intercepted = True
        response = _pick_provider_response(
            indexes,
            provider_config["provider_config_id"],
            request["dependency_name"],
            "find_package",
        )
        if response is None:
            outcome = "no_response"
        elif not response.get("satisfies", False):
            outcome = "provider_declined"
            response_id_or_null = response["response_id"]
            satisfies_or_null = False
        else:
            response_id_or_null = response["response_id"]
            satisfies_or_null = True
            if not source_version_matches(
                response.get("version_or_null"),
                request.get("version_or_null"),
                request.get("exact", False),
            ):
                version_failed = True
                outcome = "provider_declined"
            elif not _components_satisfied(
                components, response.get("provided_components", [])
            ):
                components_failed = True
                outcome = "provider_declined"
            else:
                outcome = "provider_resolved"
                return Resolution(
                    source_kind="provider",
                    identity_or_null=response["response_id"],
                    version_or_null=response.get("version_or_null"),
                    components=components,
                    produced_targets=list(response.get("produced_targets", [])),
                    provider_response_id_or_null=response["response_id"],
                    provider_satisfies_or_null=True,
                    provider_intercepted=True,
                    provider_outcome=outcome,
                )

    if owner is not None and owner.get("override_find_package"):
        if not source_version_matches(
            owner.get("declared_version_or_null"),
            request.get("version_or_null"),
            request.get("exact", False),
        ):
            version_failed = True
        elif not _fetchcontent_components_ok(components):
            components_failed = True
        else:
            return Resolution(
                source_kind="fetchcontent",
                identity_or_null=owner["declaration_id"],
                version_or_null=owner.get("declared_version_or_null"),
                components=["default"] if not components else components,
                produced_targets=list(owner.get("produced_targets", [])),
                provider_response_id_or_null=response_id_or_null,
                provider_satisfies_or_null=satisfies_or_null,
                provider_intercepted=intercepted,
                provider_outcome=outcome,
            )
    else:
        candidate = _pick_package_candidate(indexes, request["dependency_name"], request)
        if candidate is not None:
            return Resolution(
                source_kind="package",
                identity_or_null=candidate["candidate_id"],
                version_or_null=candidate["version"],
                components=components,
                produced_targets=list(candidate.get("produced_targets", [])),
                provider_response_id_or_null=response_id_or_null,
                provider_satisfies_or_null=satisfies_or_null,
                provider_intercepted=intercepted,
                provider_outcome=outcome,
            )

        if owner is not None:
            if not source_version_matches(
                owner.get("declared_version_or_null"),
                request.get("version_or_null"),
                request.get("exact", False),
            ):
                version_failed = True
            elif not _fetchcontent_components_ok(components):
                components_failed = True
            else:
                return Resolution(
                    source_kind="fetchcontent",
                    identity_or_null=owner["declaration_id"],
                    version_or_null=owner.get("declared_version_or_null"),
                    components=["default"] if not components else components,
                    produced_targets=list(owner.get("produced_targets", [])),
                    provider_response_id_or_null=response_id_or_null,
                    provider_satisfies_or_null=satisfies_or_null,
                    provider_intercepted=intercepted,
                    provider_outcome=outcome,
                )

    return Resolution(
        source_kind="not_found",
        identity_or_null=None,
        version_or_null=request.get("version_or_null"),
        components=components,
        produced_targets=[],
        provider_response_id_or_null=response_id_or_null,
        provider_satisfies_or_null=satisfies_or_null,
        provider_intercepted=intercepted,
        provider_outcome=outcome,
        version_failed=version_failed,
        components_failed=components_failed,
    )


def _resolve_make_available(
    indexes: dict[str, Any],
    project_id: str,
    request: dict[str, Any],
    provider_config: dict[str, Any],
) -> Resolution:
    norm = normalize_name(request["dependency_name"])
    owner = indexes["ownership_by_project"].get(project_id, {}).get(norm)
    components = sort_unique_components(request.get("components", []))
    bypass = request.get("bypass_provider", False)
    override = indexes["active_overrides"].get(norm)

    version_failed = False
    components_failed = False

    if override is not None:
        if not source_version_matches(
            override.get("version_or_null"),
            request.get("version_or_null"),
            request.get("exact", False),
        ):
            version_failed = True
        elif not _components_satisfied(components, override.get("provided_components", [])):
            components_failed = True
        else:
            return Resolution(
                source_kind="override",
                identity_or_null=override["override_id"],
                version_or_null=override.get("version_or_null"),
                components=components,
                produced_targets=list(override.get("produced_targets", [])),
                provider_outcome="provider_skipped",
            )

    intercepted = False
    outcome = "provider_skipped"
    response_id_or_null: str | None = None
    satisfies_or_null: bool | None = None

    intercept = (
        not bypass
        and provider_config.get("intercept_fetchcontent", False)
    )
    if intercept:
        intercepted = True
        response = _pick_provider_response(
            indexes,
            provider_config["provider_config_id"],
            request["dependency_name"],
            "make_available",
        )
        if response is None:
            outcome = "no_response"
        elif not response.get("satisfies", False):
            outcome = "provider_declined"
            response_id_or_null = response["response_id"]
            satisfies_or_null = False
        else:
            response_id_or_null = response["response_id"]
            satisfies_or_null = True
            if not source_version_matches(
                response.get("version_or_null"),
                request.get("version_or_null"),
                request.get("exact", False),
            ):
                version_failed = True
                outcome = "provider_declined"
            elif not _components_satisfied(
                components, response.get("provided_components", [])
            ):
                components_failed = True
                outcome = "provider_declined"
            else:
                outcome = "provider_resolved"
                return Resolution(
                    source_kind="provider",
                    identity_or_null=response["response_id"],
                    version_or_null=response.get("version_or_null"),
                    components=components,
                    produced_targets=list(response.get("produced_targets", [])),
                    provider_response_id_or_null=response["response_id"],
                    provider_satisfies_or_null=True,
                    provider_intercepted=True,
                    provider_outcome=outcome,
                )

    if (
        owner is not None
        and owner["find_package_args"].get("enabled")
        and owner["find_package_args"].get("try_system_first")
    ):
        candidate = _pick_package_candidate(indexes, request["dependency_name"], request)
        if candidate is not None:
            return Resolution(
                source_kind="package",
                identity_or_null=candidate["candidate_id"],
                version_or_null=candidate["version"],
                components=components,
                produced_targets=list(candidate.get("produced_targets", [])),
                provider_response_id_or_null=response_id_or_null,
                provider_satisfies_or_null=satisfies_or_null,
                provider_intercepted=intercepted,
                provider_outcome=outcome,
            )

    if owner is not None:
        fpa = owner["find_package_args"]
        decl_components = (
            sort_unique_components(fpa.get("components", []))
            if fpa.get("enabled")
            else components
        )
        decl_version = (
            fpa.get("version_or_null")
            if fpa.get("enabled")
            else owner.get("declared_version_or_null")
        )
        version_to_check = request.get("version_or_null")
        if not source_version_matches(
            decl_version, version_to_check, request.get("exact", False)
        ):
            version_failed = True
        elif not _fetchcontent_components_ok(
            components if not fpa.get("enabled") else decl_components
        ):
            components_failed = True
        elif (
            fpa.get("enabled")
            and components
            and not _components_satisfied(components, decl_components)
        ):
            components_failed = True
        else:
            if fpa.get("enabled"):
                report_components = decl_components
            elif not components:
                report_components = ["default"]
            else:
                report_components = components
            return Resolution(
                source_kind="fetchcontent",
                identity_or_null=owner["declaration_id"],
                version_or_null=decl_version,
                components=report_components,
                produced_targets=list(owner.get("produced_targets", [])),
                provider_response_id_or_null=response_id_or_null,
                provider_satisfies_or_null=satisfies_or_null,
                provider_intercepted=intercepted,
                provider_outcome=outcome,
            )

    return Resolution(
        source_kind="not_found",
        identity_or_null=None,
        version_or_null=request.get("version_or_null"),
        components=components,
        produced_targets=[],
        provider_response_id_or_null=response_id_or_null,
        provider_satisfies_or_null=satisfies_or_null,
        provider_intercepted=intercepted,
        provider_outcome=outcome,
        version_failed=version_failed,
        components_failed=components_failed,
    )


def _resolve_request(
    indexes: dict[str, Any],
    project_id: str,
    request: dict[str, Any],
    provider_config: dict[str, Any],
) -> Resolution:
    if request["request_kind"] == "find_package":
        return _resolve_find_package(indexes, project_id, request, provider_config)
    return _resolve_make_available(indexes, project_id, request, provider_config)


def _compute_closure(
    indexes: dict[str, Any],
    root_targets: list[str],
) -> tuple[list[str], list[list[str]]]:
    targets = indexes["targets"]
    edges = indexes["edges"]

    for target_id in root_targets:
        if target_id not in targets:
            raise WholeRunFatal("unknown_target_reference")

    closure: set[str] = set(root_targets)
    changed = True
    while changed:
        changed = False
        for edge in edges:
            from_t = edge["from_target"]
            to_t = edge["to_target"]
            if from_t in closure:
                if to_t not in targets:
                    raise WholeRunFatal("unknown_target_reference")
                if to_t not in closure:
                    closure.add(to_t)
                    changed = True

    closure_edges: list[list[str]] = []
    for edge in edges:
        from_t = edge["from_target"]
        to_t = edge["to_target"]
        if from_t in closure and to_t in closure:
            closure_edges.append([from_t, to_t])
    closure_edges.sort(key=lambda pair: (pair[0], pair[1]))
    return sort_unique_strings(list(closure)), closure_edges


def _has_cycle(nodes: set[str], edges: list[dict[str, Any]]) -> bool:
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    for edge in edges:
        from_t = edge["from_target"]
        to_t = edge["to_target"]
        if from_t in nodes and to_t in nodes:
            adjacency[from_t].append(to_t)

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for neighbor in adjacency.get(node, []):
            if dfs(neighbor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for node in nodes:
        if node not in visited and dfs(node):
            return True
    return False


def _declaration_preimage(owner: dict[str, Any]) -> dict[str, Any]:
    return {
        "content_digest": owner["content_digest"],
        "declaration_id": owner["declaration_id"],
        "declared_version_or_null": owner.get("declared_version_or_null"),
        "dependency_name": normalize_name(owner["dependency_name"]),
        "find_package_args": owner["find_package_args"],
        "override_find_package": owner.get("override_find_package", False),
        "produced_targets": sort_unique_strings(owner.get("produced_targets", [])),
        "source_identity": owner["source_identity"],
        "source_kind": owner["source_kind"],
    }


def _provider_preimage(
    dependency_name: str,
    request_kind: str,
    provider_config_id: str,
    bypass_provider: bool,
    response: dict[str, Any] | None,
    skipped: bool,
) -> dict[str, Any]:
    if skipped or response is None:
        return {
            "bypass_provider": bypass_provider,
            "dependency_name": normalize_name(dependency_name),
            "provider_config_id": provider_config_id,
            "request_kind": request_kind,
            "response_content_digest_or_null": None,
            "response_id_or_null": None,
            "satisfies_or_null": None,
        }
    return {
        "bypass_provider": bypass_provider,
        "dependency_name": normalize_name(dependency_name),
        "provider_config_id": provider_config_id,
        "request_kind": request_kind,
        "response_content_digest_or_null": response.get("content_digest"),
        "response_id_or_null": response["response_id"],
        "satisfies_or_null": response.get("satisfies"),
    }


def _package_selection_preimage(
    resolution: Resolution, dependency_name: str, exact: bool
) -> dict[str, Any]:
    identity = None
    if resolution.source_kind == "package":
        identity = resolution.identity_or_null
    elif resolution.source_kind == "provider":
        identity = resolution.identity_or_null
    elif resolution.source_kind == "fetchcontent":
        identity = resolution.identity_or_null
    elif resolution.source_kind == "override":
        identity = resolution.identity_or_null
    return {
        "candidate_id_or_null": identity if resolution.source_kind == "package" else None,
        "components": sort_unique_components(resolution.components),
        "dependency_name": normalize_name(dependency_name),
        "exact": exact,
        "source_kind": resolution.source_kind,
        "version_or_null": resolution.version_or_null,
    }


def _target_graph_preimage(
    dependency_name: str,
    root_targets: list[str],
    closure_targets: list[str],
    closure_edges: list[list[str]],
) -> dict[str, Any]:
    return {
        "closure_targets": sort_unique_strings(closure_targets),
        "dependency_name": normalize_name(dependency_name),
        "edges": closure_edges,
        "root_targets": sort_unique_strings(root_targets),
    }


def _final_resolution_preimage(
    dependency_name: str,
    declaration_digest: str,
    provider_digest: str,
    package_digest: str,
    target_graph_digest: str,
) -> dict[str, Any]:
    return {
        "dependency_name": normalize_name(dependency_name),
        "declaration_result_digest": declaration_digest,
        "package_selection_result_digest": package_digest,
        "provider_result_digest": provider_digest,
        "target_graph_result_digest": target_graph_digest,
    }


def _stored_declaration(owner: dict[str, Any]) -> dict[str, Any]:
    return {"declaration_id": owner["declaration_id"], "ownership": "owner"}


def _stored_provider(resolution: Resolution) -> dict[str, Any]:
    if resolution.source_kind == "provider":
        return {
            "response_id_or_null": resolution.identity_or_null,
            "source_kind": "provider",
        }
    return {"response_id_or_null": None, "source_kind": "skipped"}


def _stored_package_selection(resolution: Resolution) -> dict[str, Any]:
    identity = resolution.identity_or_null
    return {"source_kind": resolution.source_kind, "identity": identity}


def _stored_target_graph(closure_targets: list[str]) -> dict[str, Any]:
    return {"closure_targets": sort_unique_strings(closure_targets)}


def _stored_final_resolution(source_kind: str, action_hint: str) -> dict[str, Any]:
    return {"action_hint": action_hint, "source_kind": source_kind}


def _rejection_reason(resolution: Resolution) -> str:
    if resolution.components_failed:
        return "components_unsatisfied"
    if resolution.version_failed:
        return "version_mismatch"
    return "unresolved_dependency"


def _process_configure_request(
    indexes: dict[str, Any],
    cfg: dict[str, Any],
) -> ConfigureState:
    provider_config = indexes["providers"][cfg["provider_config_id"]]
    previous_lock = None
    if cfg.get("previous_lock_id_or_null") is not None:
        previous_lock = indexes["locks"][cfg["previous_lock_id_or_null"]]

    find_requests = [
        indexes["find_by_id"][find_id] for find_id in cfg["find_request_ids"]
    ]

    state = ConfigureState(
        configure_request_id=cfg["configure_request_id"],
        request_index=cfg["request_index"],
        project_id=cfg["project_id"],
        provider_config_id=cfg["provider_config_id"],
        lock_mode=cfg["lock_mode"],
        previous_lock=previous_lock,
        find_requests=find_requests,
    )

    producer_map: dict[str, str] = {}
    all_closure_nodes: set[str] = set()

    for request in find_requests:
        resolution = _resolve_request(
            indexes, cfg["project_id"], request, provider_config
        )
        norm = normalize_name(request["dependency_name"])
        state.resolutions[norm] = resolution

        state.provider_rows.append(
            {
                "configure_request_id": cfg["configure_request_id"],
                "find_request_id": request["find_request_id"],
                "dependency_name": norm,
                "intercepted": resolution.provider_intercepted,
                "bypass_provider": request.get("bypass_provider", False),
                "response_id_or_null": resolution.provider_response_id_or_null,
                "satisfies_or_null": resolution.provider_satisfies_or_null,
                "outcome": resolution.provider_outcome,
            }
        )

        report_components = sort_unique_components(resolution.components)
        state.package_selection_rows.append(
            {
                "configure_request_id": cfg["configure_request_id"],
                "find_request_id": request["find_request_id"],
                "dependency_name": norm,
                "source_kind": resolution.source_kind,
                "identity_or_null": resolution.identity_or_null,
                "version_or_null": resolution.version_or_null,
                "components": report_components,
            }
        )

        if resolution.source_kind == "not_found":
            if request.get("required", True):
                reason = _rejection_reason(resolution)
                state.rejections.append(
                    {
                        "configure_request_id": cfg["configure_request_id"],
                        "find_request_id_or_null": request["find_request_id"],
                        "reason_token": reason,
                        "message": f"{reason} for {norm}",
                    }
                )
                state.rejected = True
            closure_targets: list[str] = []
            closure_edges: list[list[str]] = []
        else:
            state.resolved_dependency_count += 1
            for target_id in resolution.produced_targets:
                if target_id in producer_map and producer_map[target_id] != norm:
                    raise WholeRunFatal("duplicate_target_producer")
                producer_map[target_id] = norm

            closure_targets, closure_edges = _compute_closure(
                indexes, resolution.produced_targets
            )
            all_closure_nodes.update(closure_targets)

            for target_id in closure_targets:
                role = "root" if target_id in resolution.produced_targets else "transitive"
                producer = indexes["targets"][target_id]["producer_dependency"]
                state.target_rows.append(
                    {
                        "configure_request_id": cfg["configure_request_id"],
                        "dependency_name": norm,
                        "target_id": target_id,
                        "role": role,
                        "producer_dependency": producer,
                    }
                )

        owner = indexes["ownership_by_project"].get(cfg["project_id"], {}).get(norm)
        prior_sections = {}
        if previous_lock is not None:
            prior_sections = previous_lock.get("sections_by_dependency", {}).get(norm, {})

        decl_input = None
        decl_result = None
        decl_digest_in = None
        decl_digest_out = None
        if owner is not None:
            decl_input = _declaration_preimage(owner)
            decl_result = _stored_declaration(owner)
            decl_digest_in = sha256_hex(decl_input)
            decl_digest_out = sha256_hex(decl_result)

        provider_skipped = (
            norm in indexes["active_overrides"]
            or request.get("bypass_provider", False)
            or (
                request["request_kind"] == "find_package"
                and not provider_config.get("intercept_find_package", False)
            )
            or (
                request["request_kind"] == "make_available"
                and not provider_config.get("intercept_fetchcontent", False)
            )
        )
        provider_response = None
        if not provider_skipped:
            provider_response = _pick_provider_response(
                indexes,
                provider_config["provider_config_id"],
                request["dependency_name"],
                request["request_kind"],
            )
        prov_input = _provider_preimage(
            request["dependency_name"],
            request["request_kind"],
            provider_config["provider_config_id"],
            request.get("bypass_provider", False),
            provider_response,
            provider_skipped,
        )
        prov_result = _stored_provider(resolution)
        prov_digest_in = sha256_hex(prov_input)
        prov_digest_out = sha256_hex(prov_result)

        pkg_input = _package_selection_preimage(
            resolution, request["dependency_name"], request.get("exact", False)
        )
        pkg_result = _stored_package_selection(resolution)
        pkg_digest_in = sha256_hex(pkg_input)
        pkg_digest_out = sha256_hex(pkg_result)

        tg_input = _target_graph_preimage(
            norm,
            resolution.produced_targets,
            closure_targets,
            closure_edges,
        )
        tg_result = _stored_target_graph(closure_targets)
        tg_digest_in = sha256_hex(tg_input)
        tg_digest_out = sha256_hex(tg_result)

        section_specs = [
            ("declaration", decl_digest_in, decl_digest_out, owner is not None),
            ("provider", prov_digest_in, prov_digest_out, True),
            ("package_selection", pkg_digest_in, pkg_digest_out, True),
            ("target_graph", tg_digest_in, tg_digest_out, True),
        ]

        section_results: dict[str, tuple[str, str]] = {}
        stale_sections: set[str] = set()

        for section_name, input_digest, result_digest, applicable in section_specs:
            if not applicable:
                stale_sections.add(section_name)
                continue
            prior = prior_sections.get(section_name)
            if prior is None:
                stale_sections.add(section_name)
            elif (
                prior.get("input_digest") != input_digest
                or prior.get("result_digest") != result_digest
            ):
                stale_sections.add(section_name)
            section_results[section_name] = (input_digest, result_digest)

        cascade_map = {
            "declaration": {"provider", "package_selection", "target_graph", "final_resolution"},
            "provider": {"package_selection", "target_graph", "final_resolution"},
            "package_selection": {"target_graph", "final_resolution"},
            "target_graph": {"final_resolution"},
            "final_resolution": set(),
        }
        recompute: set[str] = set()
        queue = list(stale_sections)
        while queue:
            section = queue.pop()
            if section in recompute:
                continue
            recompute.add(section)
            for downstream in cascade_map.get(section, set()):
                if downstream not in recompute:
                    queue.append(downstream)

        final_action_hint = "reuse"
        if recompute:
            final_action_hint = "update"
        decl_digest = (
            section_results.get("declaration", ("", ""))[1]
            if "declaration" in section_results
            else ""
        )
        final_input = _final_resolution_preimage(
            norm,
            decl_digest,
            section_results.get("provider", ("", ""))[1],
            section_results.get("package_selection", ("", ""))[1],
            section_results.get("target_graph", ("", ""))[1],
        )
        final_result = _stored_final_resolution(resolution.source_kind, final_action_hint)
        final_digest_in = sha256_hex(final_input)
        final_digest_out = sha256_hex(final_result)

        prior_final = prior_sections.get("final_resolution")
        if prior_final is None or (
            prior_final.get("input_digest") != final_digest_in
            or prior_final.get("result_digest") != final_digest_out
        ):
            stale_sections.add("final_resolution")
            recompute.add("final_resolution")

        if cfg["lock_mode"] == "error" and stale_sections:
            state.rejections.append(
                {
                    "configure_request_id": cfg["configure_request_id"],
                    "find_request_id_or_null": request["find_request_id"],
                    "reason_token": "stale_lock_section",
                    "message": f"stale_lock_section for {norm}",
                }
            )
            state.rejected = True
            for section_name in SECTION_NAMES:
                input_digest = ""
                result_digest = ""
                disposition = "rejected_stale"
                if section_name == "declaration" and owner is not None:
                    input_digest = decl_digest_in or ""
                    result_digest = decl_digest_out or ""
                elif section_name == "provider":
                    input_digest = prov_digest_in
                    result_digest = prov_digest_out
                elif section_name == "package_selection":
                    input_digest = pkg_digest_in
                    result_digest = pkg_digest_out
                elif section_name == "target_graph":
                    input_digest = tg_digest_in
                    result_digest = tg_digest_out
                elif section_name == "final_resolution":
                    input_digest = final_digest_in
                    result_digest = final_digest_out
                state.lock_section_rows.append(
                    {
                        "configure_request_id": cfg["configure_request_id"],
                        "dependency_name": norm,
                        "section": section_name,
                        "input_digest": input_digest,
                        "result_digest": result_digest,
                        "disposition": disposition,
                    }
                )
            continue

        for section_name in SECTION_NAMES:
            if section_name == "declaration" and owner is None:
                continue
            if section_name == "declaration":
                input_digest = decl_digest_in or ""
                result_digest = decl_digest_out or ""
            elif section_name == "provider":
                input_digest = prov_digest_in
                result_digest = prov_digest_out
            elif section_name == "package_selection":
                input_digest = pkg_digest_in
                result_digest = pkg_digest_out
            elif section_name == "target_graph":
                input_digest = tg_digest_in
                result_digest = tg_digest_out
            else:
                input_digest = final_digest_in
                result_digest = final_digest_out

            prior = prior_sections.get(section_name)
            reusable = (
                prior is not None
                and prior.get("input_digest") == input_digest
                and prior.get("result_digest") == result_digest
                and section_name not in recompute
            )
            if reusable:
                disposition = "reused"
                state.reused_section_count += 1
            else:
                disposition = "updated"
                state.updated_section_count += 1

            state.lock_section_rows.append(
                {
                    "configure_request_id": cfg["configure_request_id"],
                    "dependency_name": norm,
                    "section": section_name,
                    "input_digest": input_digest,
                    "result_digest": result_digest,
                    "disposition": disposition,
                }
            )

    if _has_cycle(all_closure_nodes, indexes["edges"]):
        raise WholeRunFatal("target_dependency_cycle")

    if state.rejected:
        state.action = "reject_configuration"
    elif state.updated_section_count > 0:
        state.action = "update_resolution"
    else:
        state.action = "reuse_resolution"

    return state


def _build_declaration_rows(indexes: dict[str, Any], project_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decl in indexes["declarations"]:
        if decl["project_id"] not in project_ids:
            continue
        ownership = (
            "shadowed"
            if decl["declaration_id"] in indexes["shadowed_ids"]
            else "owner"
        )
        rows.append(
            {
                "declaration_id": decl["declaration_id"],
                "project_id": decl["project_id"],
                "dependency_name": normalize_name(decl["dependency_name"]),
                "declaration_index": decl["declaration_index"],
                "ownership": ownership,
                "override_find_package": decl.get("override_find_package", False),
                "find_package_args_enabled": decl["find_package_args"].get("enabled", False),
            }
        )
    rows.sort(key=lambda r: (r["project_id"], r["declaration_index"], r["declaration_id"]))
    return rows


def reconcile(data_dir: Path) -> dict[str, Any]:
    """Run the full reconciliation profile and return the report dict."""
    try:
        data = load_data_dir(data_dir)
    except MissingRequiredInputError as exc:
        raise WholeRunFatal("missing_required_input") from exc
    except MalformedJsonError as exc:
        raise WholeRunFatal("malformed_json") from exc

    try:
        indexes = _build_indexes(data)
    except InvalidVersionError as exc:
        raise WholeRunFatal("invalid_version") from exc

    configure_states: list[ConfigureState] = []
    project_ids: set[str] = set()

    for cfg in indexes["configure_requests"]:
        project_ids.add(cfg["project_id"])
        configure_states.append(_process_configure_request(indexes, cfg))

    request_rows = [
        {
            "configure_request_id": state.configure_request_id,
            "request_index": state.request_index,
            "project_id": state.project_id,
            "provider_config_id": state.provider_config_id,
            "lock_mode": state.lock_mode,
            "action": state.action,
            "resolved_dependency_count": state.resolved_dependency_count,
            "reused_section_count": state.reused_section_count,
            "updated_section_count": state.updated_section_count,
        }
        for state in configure_states
    ]

    provider_rows: list[dict[str, Any]] = []
    package_selection_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    lock_section_rows: list[dict[str, Any]] = []
    rejection_rows: list[dict[str, Any]] = []

    for state in configure_states:
        provider_rows.extend(state.provider_rows)
        package_selection_rows.extend(state.package_selection_rows)
        target_rows.extend(state.target_rows)
        lock_section_rows.extend(state.lock_section_rows)
        rejection_rows.extend(state.rejections)

    provider_rows.sort(key=lambda r: (r["configure_request_id"], r["find_request_id"]))
    package_selection_rows.sort(
        key=lambda r: (r["configure_request_id"], r["find_request_id"])
    )
    target_rows.sort(
        key=lambda r: (r["configure_request_id"], r["dependency_name"], r["target_id"])
    )
    lock_section_rows.sort(
        key=lambda r: (
            r["configure_request_id"],
            r["dependency_name"],
            SECTION_ORDER[r["section"]],
        )
    )
    rejection_rows.sort(
        key=lambda r: (
            r["configure_request_id"],
            r["find_request_id_or_null"] or "",
            r["reason_token"],
        )
    )

    declaration_rows = _build_declaration_rows(indexes, project_ids)
    declaration_owner_count = sum(1 for row in declaration_rows if row["ownership"] == "owner")

    summary = {
        "configure_request_count": len(configure_states),
        "reuse_count": sum(1 for s in configure_states if s.action == "reuse_resolution"),
        "update_count": sum(1 for s in configure_states if s.action == "update_resolution"),
        "reject_count": sum(1 for s in configure_states if s.action == "reject_configuration"),
        "declaration_owner_count": declaration_owner_count,
        "target_row_count": len(target_rows),
    }

    return {
        "schema_version": 1,
        "request_rows": request_rows,
        "declaration_rows": declaration_rows,
        "provider_rows": provider_rows,
        "package_selection_rows": package_selection_rows,
        "target_rows": target_rows,
        "lock_section_rows": lock_section_rows,
        "rejection_rows": rejection_rows,
        "summary": summary,
    }
