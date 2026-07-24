"""Seeded inventory and profile fixtures for aurora synthesis tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

TEST_SEEDS: dict[str, int] = {
    "visible_current": 1001,
    "inherit_prof": 2001,
    "legacy_v1": 3001,
    "filter_chain": 4001,
    "codec_matrix": 5001,
    "miss_caps": 6001,
    "subtitle_modes": 7001,
    "ambig_burn": 8001,
    "inventory_order": 9001,
    "cache_sens": 10001,
    "dependency_lock": 11001,
    "makefile_parse": 12001,
    "make_exec": 13001,
    "txn_fail": 14001,
    "check_mode": 15001,
}


def seed_for(case_id: str) -> int:
    """Return the deterministic RNG seed for a named fixture case."""
    return TEST_SEEDS[case_id]


INVALID_BURN_IN_PROFILE = "bad"


def _digest(seed: int, label: str) -> str:
    return f"sha256:{hashlib.sha256(f'{seed}:{label}'.encode()).hexdigest()}"


def _asset(seed: int, asset_id: str, **overrides: Any) -> dict[str, Any]:
    video = {
        "width": 1920,
        "height": 1080,
        "fps": "24/1",
        "pix_fmt": "yuv420p",
        "color_transfer": "bt709",
        "has_alpha": False,
        "rotation": 0,
    }
    video.update(overrides.pop("video", {}))
    asset: dict[str, Any] = {
        "id": asset_id,
        "relative_path": overrides.get("relative_path", f"clips/{asset_id}.mp4"),
        "content_digest": _digest(seed, f"asset:{asset_id}"),
        "video": video,
        "audio_tracks": [{"index": 0, "language": "en", "channels": 2}],
        "subtitle_tracks": overrides.get(
            "subtitle_tracks",
            [
                {
                    "index": 1,
                    "language": "en",
                    "relative_path": f"subs/{asset_id}.en.srt",
                    "content_digest": _digest(seed, f"sub:{asset_id}:en"),
                },
                {
                    "index": 2,
                    "language": "fr",
                    "relative_path": f"subs/{asset_id}.fr.srt",
                    "content_digest": _digest(seed, f"sub:{asset_id}:fr"),
                },
            ],
        ),
    }
    asset.update({k: v for k, v in overrides.items() if k not in {"video"}})
    return asset


def make_inventory(seed: int, *, source_root: str = "/data/media", **overrides: Any) -> dict[str, Any]:
    inv: dict[str, Any] = {
        "format": "aurora-inventory-v2",
        "source_root": source_root,
        "assets": [
            _asset(seed, "hero"),
            _asset(
                seed,
                "hdr-clip",
                video={
                    "pix_fmt": "yuv420p10le",
                    "color_transfer": "smpte2084",
                    "width": 3840,
                    "height": 2160,
                    "rotation": 90,
                },
            ),
        ],
    }
    inv.update(overrides)
    return inv


def make_profiles_v3(seed: int, **overrides: Any) -> dict[str, Any]:
    _ = seed
    doc: dict[str, Any] = {
        "format": "aurora-profiles-v3",
        "profiles": {
            "web-base": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {"target_width": 1280, "target_height": 720, "tone_map": False},
                "subtitles": {"mode": "sidecar", "languages": ["en"]},
            },
            "web-derived": {
                "extends": "web-base",
                "video": {"target_width": 640, "target_height": 360, "tone_map": True},
            },
        },
        "jobs": [{"asset_id": "hero", "profile": "web-base", "artifact_name": "hero-web"}],
    }
    doc.update(overrides)
    return doc


def make_inheritance_profiles() -> dict[str, Any]:
    return {
        "format": "aurora-profiles-v3",
        "profiles": {
            "parent": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {
                    "target_width": 1920,
                    "target_height": 1080,
                    "tone_map": True,
                    "trim_in_ms": 100,
                    "trim_out_ms": 900,
                    "setpts": "PTS",
                    "crop": "in_w:in_h:0:0",
                    "fps": "30/1",
                    "sar": "1:1",
                },
                "audio": {"normalization": {"target_lufs": -16}},
                "subtitles": {"mode": "sidecar", "languages": ["en", "fr"]},
            },
            "child": {
                "extends": "parent",
                "video": {
                    "tone_map": False,
                    "trim_in_ms": 0,
                    "trim_out_ms": 0,
                    "setpts": "",
                    "crop": None,
                    "target_width": 0,
                    "target_height": 0,
                    "fps": 0,
                    "sar": "",
                },
                "audio": {"normalization": None},
                "subtitles": {"mode": None, "languages": []},
            },
        },
        "jobs": [{"asset_id": "hero", "profile": "child", "artifact_name": "inherit-child"}],
    }


def make_legacy_profiles_file(seed: int) -> dict[str, Any]:
    _ = seed
    return {
        "format": "aurora-profile-v1",
        "profiles": {
            "legacy-web": {
                "delivery_profile": "web-sdr",
                "container": "mp4",
                "width": 1280,
                "height": 720,
                "fps": "30/1",
            }
        },
        "jobs": [{"asset_id": "hero", "profile": "legacy-web", "artifact_name": "legacy-hero"}],
    }


def make_filter_chain_profiles() -> dict[str, Any]:
    return {
        "format": "aurora-profiles-v3",
        "profiles": {
            "filter-heavy": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {
                    "target_width": 1080,
                    "target_height": 1080,
                    "tone_map": True,
                    "fps": "25/1",
                    "crop": "in_w:in_h:0:0",
                    "setpts": "PTS-STARTPTS",
                },
                "subtitles": {"mode": "burn_in", "burn_in_language": "en"},
            }
        },
        "jobs": [{"asset_id": "hdr-clip", "profile": "filter-heavy", "artifact_name": "hdr-square"}],
    }


def make_codec_matrix_inventory(seed: int) -> dict[str, Any]:
    return {
        "format": "aurora-inventory-v2",
        "source_root": "/data/codec-matrix",
        "assets": [
            _asset(seed, "sdr-clip"),
            _asset(
                seed,
                "hdr-clip",
                video={"color_transfer": "smpte2084", "pix_fmt": "yuv420p10le"},
            ),
            _asset(seed, "alpha-clip", video={"has_alpha": True, "pix_fmt": "rgba"}),
            _asset(seed, "audio-only", video={"width": 1, "height": 1}),
        ],
    }


def make_codec_matrix_profiles() -> dict[str, Any]:
    return {
        "format": "aurora-profiles-v3",
        "profiles": {
            "web-sdr": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {"target_width": 1280, "target_height": 720, "tone_map": False},
                "subtitles": {"mode": "none"},
            },
            "web-hdr": {
                "output": {"delivery_profile": "web-hdr", "container": "mp4"},
                "video": {"target_width": 1920, "target_height": 1080},
                "subtitles": {"mode": "none"},
            },
            "archive": {
                "output": {"delivery_profile": "archive", "container": "mov"},
                "video": {"target_width": 1920, "target_height": 1080},
                "subtitles": {"mode": "none"},
            },
            "audio-preview": {
                "output": {"delivery_profile": "audio-preview", "container": "m4a"},
                "subtitles": {"mode": "none"},
            },
        },
    }


def make_subtitle_profiles(mode: str, languages: list[str], burn_lang: str | None) -> dict[str, Any]:
    return {
        "format": "aurora-profiles-v3",
        "profiles": {
            "sub-profile": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {"target_width": 1280, "target_height": 720},
                "subtitles": {
                    "mode": mode,
                    "languages": languages,
                    "burn_in_language": burn_lang,
                },
            }
        },
        "jobs": [{"asset_id": "hero", "profile": "sub-profile", "artifact_name": "hero-sub"}],
    }


def make_invalid_cross_field_profiles() -> dict[str, Any]:
    return {
        "format": "aurora-profiles-v3",
        "profiles": {
            INVALID_BURN_IN_PROFILE: {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {"target_width": 1280, "target_height": 720},
                "subtitles": {"mode": "burn_in", "burn_in_language": None},
            }
        },
        "jobs": [
            {
                "asset_id": "hero",
                "profile": INVALID_BURN_IN_PROFILE,
                "artifact_name": INVALID_BURN_IN_PROFILE,
            }
        ],
    }


def reorder_inventory_entries(inventory: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(inventory)
    assets = out.get("assets", [])
    out["assets"] = list(reversed(assets))
    # shuffle key order by re-serializing
    raw = json.dumps(out, sort_keys=False)
    return json.loads(raw)


def write_fixture_bundle(
    root: Path,
    *,
    inventory: dict[str, Any],
    profiles: dict[str, Any],
    profiles_name: str = "profiles.yaml",
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    inv_path = root / "inventory.json"
    prof_path = root / profiles_name
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    if profiles_name.endswith(".yaml"):
        prof_path.write_text(yaml.safe_dump(profiles, sort_keys=False), encoding="utf-8")
    else:
        prof_path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
    return {"inventory": inv_path, "profiles": prof_path}


def run_argv(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    check = bool(kwargs.pop("check", False))
    return subprocess.run(argv, check=check, **kwargs)
