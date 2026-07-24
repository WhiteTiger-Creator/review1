"""Independent reference semantics aligned with the aurora-build public contract."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

SET_LIKE_PATHS = {
    ("capabilities", "encoders"),
    ("capabilities", "filters"),
    ("capabilities", "muxers"),
    ("subtitles", "languages"),
}


def codepoint_sort(values: list[str]) -> list[str]:
    return sorted(values, key=lambda item: [ord(ch) for ch in item])


def canonicalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {k: canonicalize(v, path + (k,)) for k, v in sorted(value.items())}
    if isinstance(value, list):
        if path in SET_LIKE_PATHS and all(isinstance(x, str) for x in value):
            return codepoint_sort(value)
        return [canonicalize(v, path) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonicalize(value), separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def sha256_prefixed(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def fingerprint_lock(body: dict[str, Any]) -> str:
    return sha256_prefixed(canonical_json(body))


def merge_presence(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(parent)
    for key, child_val in child.items():
        if key == "extends":
            continue
        if child_val is None:
            result.pop(key, None)
            continue
        if isinstance(child_val, list):
            result[key] = deepcopy(child_val)
            continue
        if isinstance(child_val, dict) and isinstance(result.get(key), dict):
            result[key] = merge_presence(result[key], child_val)
            continue
        result[key] = deepcopy(child_val)
    return result


def adapt_legacy_v1_profile(flat: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": {
            "delivery_profile": flat.get("delivery_profile", "web-sdr"),
            "container": flat.get("container"),
        },
        "video": {
            "target_width": flat.get("width"),
            "target_height": flat.get("height"),
            "fps": flat.get("fps"),
            "crop": flat.get("crop"),
            "tone_map": flat.get("tone_map", False),
            "trim_in_ms": flat.get("trim_in_ms"),
            "trim_out_ms": flat.get("trim_out_ms"),
            "setpts": flat.get("setpts"),
            "sar": flat.get("sar"),
        },
        "audio": {
            "normalization": flat.get("audio_normalization") if "audio_normalization" in flat else None,
            "language": flat.get("audio_language"),
        },
        "subtitles": {
            "mode": flat.get("subtitle_mode", "none"),
            "languages": list(flat.get("subtitle_languages", [])),
            "burn_in_language": flat.get("burn_in_language"),
        },
    }


def resolve_profile(profiles_doc: dict[str, Any], name: str, stack: list[str] | None = None) -> dict[str, Any]:
    profiles = profiles_doc.get("profiles", {})
    if name not in profiles:
        raise KeyError(f"unknown profile: {name}")
    stack = list(stack or [])
    if name in stack:
        raise ValueError("profile cycle")
    node = deepcopy(profiles[name])
    if node.get("format") == "aurora-profile-v1":
        node = adapt_legacy_v1_profile(node)
    parent_name = node.pop("extends", None)
    base: dict[str, Any] = {}
    if parent_name:
        base = resolve_profile(profiles_doc, parent_name, stack + [name])
    return merge_presence(base, node)


def is_hdr_asset(asset: dict[str, Any]) -> bool:
    ct = (asset.get("video") or {}).get("color_transfer")
    return ct in {"smpte2084", "arib-std-b67", "hdr"}


def select_codecs(asset: dict[str, Any], resolved: dict[str, Any], capabilities: dict[str, list[str]]) -> dict[str, Any]:
    delivery = (resolved.get("output") or {}).get("delivery_profile", "web-sdr")
    encoders = set(capabilities.get("encoders", []))
    muxers = set(capabilities.get("muxers", []))
    alpha = bool((asset.get("video") or {}).get("has_alpha"))
    hdr = is_hdr_asset(asset)
    tone_map = bool((resolved.get("video") or {}).get("tone_map"))

    def require(name: str, pool: set[str]) -> None:
        if name not in pool:
            raise ValueError(f"missing capability: {name}")

    if delivery == "audio-preview":
        require("aac", encoders)
        require("ipod", muxers)
        return {"container": "m4a", "video": None, "audio": {"codec": "aac"}}

    if delivery == "web-hdr":
        require("libx265", encoders)
        require("mp4", muxers)
        return {
            "container": "mp4",
            "video": {"codec": "libx265", "pixel_format": "yuv420p10le", "tag": "hvc1"},
            "audio": {"codec": "aac"},
        }

    if delivery == "archive":
        require("prores_ks", encoders)
        require("mov", muxers)
        if alpha:
            return {
                "container": "mov",
                "video": {"codec": "prores_ks", "profile": 4, "pixel_format": "yuva444p10le"},
                "audio": {"codec": "pcm_s24le"},
            }
        return {
            "container": "mov",
            "video": {"codec": "prores_ks", "profile": 3, "pixel_format": "yuv422p10le"},
            "audio": {"codec": "pcm_s24le"},
        }

    require("libx264", encoders)
    require("mp4", muxers)
    return {
        "container": (resolved.get("output") or {}).get("container") or "mp4",
        "video": {
            "codec": "libx264",
            "pixel_format": "yuv420p",
            "tone_map_chain": hdr and tone_map,
        },
        "audio": {"codec": "aac"},
    }


def plan_filters(asset: dict[str, Any], resolved: dict[str, Any], codec_selection: dict[str, Any]) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    video = resolved.get("video") or {}
    rotation = (asset.get("video") or {}).get("rotation", 0)

    def push(phase: int, name: str, args: str) -> None:
        seq = sum(1 for f in filters if f["phase"] == phase) + 1
        filters.append({"phase": phase, "sequence": seq, "name": name, "args": args})

    if rotation == 90:
        push(10, "transpose", "1")
    elif rotation == 180:
        push(10, "transpose", "1")
        push(10, "transpose", "1")
    elif rotation == 270:
        push(10, "transpose", "2")

    if video.get("trim_in_ms") is not None or video.get("trim_out_ms") is not None:
        start = (video.get("trim_in_ms") or 0) / 1000
        end = video.get("trim_out_ms")
        push(20, "trim", f"start={start:.3f}" + (f":end={end/1000:.3f}" if end is not None else ""))

    if video.get("setpts"):
        push(30, "setpts", str(video["setpts"]))
    if video.get("crop"):
        push(40, "crop", str(video["crop"]))
    if video.get("target_width") and video.get("target_height"):
        push(40, "scale", f"{video['target_width']}:{video['target_height']}")

    if is_hdr_asset(asset) and video.get("tone_map") and (codec_selection.get("video") or {}).get("tone_map_chain"):
        push(50, "zscale", "transfer=linear:npl=100")
        push(50, "tonemap", "tonemap=hable:desat=0")
        push(50, "zscale", "transfer=bt709:matrix=bt709:primaries=bt709")

    if video.get("fps"):
        push(60, "fps", str(video["fps"]))

    subtitles = resolved.get("subtitles") or {}
    if subtitles.get("mode") == "burn_in" and subtitles.get("burn_in_language"):
        push(70, "subtitles", f"filename={subtitles['burn_in_language']}")

    if video.get("sar"):
        push(80, "setsar", str(video["sar"]))

    pix = (codec_selection.get("video") or {}).get("pixel_format")
    if pix:
        push(90, "format", pix)

    return filters


def cache_key_payload(asset: dict[str, Any], resolved: dict[str, Any], filters: list[dict[str, Any]], lock_fingerprint: str) -> str:
    body = {
        "content_digest": asset["content_digest"],
        "resolved_profile": resolved,
        "filters": filters,
        "lock_fingerprint": lock_fingerprint,
    }
    return sha256_prefixed(canonical_json(body))


def dependency_lock_from_probe(probe: dict[str, Any]) -> dict[str, Any]:
    body = {
        "format": "aurora-dependency-lock-v1",
        "executable": probe["executable"],
        "binary_digest": probe["binary_digest"],
        "version": probe.get("version") or probe.get("version_line", "").replace("ffmpeg version ", "").split()[0],
        "capabilities": {
            "encoders": codepoint_sort(list(probe.get("encoders", probe.get("capabilities", {}).get("encoders", [])))),
            "filters": codepoint_sort(list(probe.get("filters", probe.get("capabilities", {}).get("filters", [])))),
            "muxers": codepoint_sort(list(probe.get("muxers", probe.get("capabilities", {}).get("muxers", [])))),
        },
    }
    fp = fingerprint_lock({k: v for k, v in body.items() if k != "fingerprint"})
    return {**body, "fingerprint": fp}
