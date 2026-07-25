from __future__ import annotations

from rt_core.lane_d.caps_lane import combine_sets, min_limits
from rt_core.lane_k.ver_lane import expand_decl


def resolve_caps(abi: int, manifest: dict, policy_view: dict, grant: dict) -> set[str]:
    manifest_caps = expand_decl(abi, set(manifest.get("capabilities", [])))
    policy_caps = set(policy_view.get("capabilities", []))
    grant_caps = set(grant.get("capabilities", [])) if grant else None
    return combine_sets(manifest_caps, policy_caps, grant_caps)


def resolve_limits(manifest: dict, policy_view: dict, grant: dict) -> dict:
    return min_limits(
        manifest.get("limits", {}),
        policy_view.get("limits", {}),
        grant.get("limits") if grant else None,
    )
