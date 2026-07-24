"""Create deterministic fake ffmpeg executables for verifier-controlled probes."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

# Capability bundles referenced by fixture seeds and failure tests.
CAPABILITY_PROFILES: dict[str, dict[str, list[str]]] = {
    "full": {
        "encoders": [
            "aac",
            "libx264",
            "libx265",
            "prores_ks",
        ],
        "filters": [
            "crop",
            "format",
            "fps",
            "loudnorm",
            "scale",
            "setpts",
            "setsar",
            "subtitles",
            "tonemap",
            "transpose",
            "trim",
            "zscale",
        ],
        "muxers": [
            "ipod",
            "mov",
            "mp4",
        ],
    },
    "no_libx265": {
        "encoders": ["aac", "libx264", "prores_ks"],
        "filters": [
            "crop",
            "format",
            "fps",
            "loudnorm",
            "scale",
            "setpts",
            "setsar",
            "subtitles",
            "tonemap",
            "transpose",
            "trim",
            "zscale",
        ],
        "muxers": ["ipod", "mov", "mp4"],
    },
    "no_tonemap": {
        "encoders": ["aac", "libx264", "libx265", "prores_ks"],
        "filters": [
            "crop",
            "format",
            "fps",
            "loudnorm",
            "scale",
            "setpts",
            "setsar",
            "subtitles",
            "transpose",
            "trim",
            "zscale",
        ],
        "muxers": ["ipod", "mov", "mp4"],
    },
    "minimal_audio": {
        "encoders": ["aac"],
        "filters": ["loudnorm"],
        "muxers": ["ipod"],
    },
}

_FAKE_FFMPEG_TEMPLATE = '''#!/usr/bin/env python3
import json
import os
import sys

PROFILE = json.loads({profile_json!r})
VERSION = {version!r}

def _log(argv):
    log_path = os.environ.get("FFMPEG_LOG")
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(" ".join(argv) + "\\n")

def _list_block(kind, names):
    # Match stock ffmpeg listing shape: legend, ------ separator, then
    # flag-column + name (+ optional description). Flag width is six chars
    # for encoders/filters-style lines (same as Debian ffmpeg).
    lines = [kind + ":"]
    if kind == "Encoders":
        lines.extend([
            " V..... = Video",
            " A..... = Audio",
            " S..... = Subtitle",
            " .F.... = Frame-level multithreading",
            " ..S... = Slice-level multithreading",
            " ...X.. = Experimental",
            " ....B. = Supports draw_horiz_band",
            " .....D = Supports direct rendering method 1",
            " ------",
        ])
        flag = " A....."
    elif kind == "Filters":
        lines.extend([
            " T.. = Timeline support",
            " S.. = Slice threading",
            " A = Audio",
            " V = Video",
            " ------",
        ])
        flag = " ..S"
    else:
        lines.extend([
            " D. = Demuxing supported",
            " .E = Muxing supported",
            " ------",
        ])
        flag = "  E"
    for name in names:
        lines.append(flag + " " + name + "                 " + name)
    return "\\n".join(lines) + "\\n"

def main():
    argv = sys.argv[:]
    _log(argv)
    if "-version" in argv:
        print("ffmpeg version " + VERSION + " aurora-fake")
        print("configuration: --enable-gpl --enable-libx264 --enable-libx265")
        return 0
    if "-encoders" in argv:
        sys.stdout.write(_list_block("Encoders", PROFILE["encoders"]))
        return 0
    if "-filters" in argv:
        sys.stdout.write(_list_block("Filters", PROFILE["filters"]))
        return 0
    if "-muxers" in argv:
        sys.stdout.write(_list_block("Muxers", PROFILE["muxers"]))
        return 0
    if "-h" in argv or "-?" in argv:
        print("aurora fake ffmpeg")
        return 0
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


def binary_digest(path: Path) -> str:
    """Return sha256 digest for a fake ffmpeg binary."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


_DEFAULT_CAPABILITY = "full"
_DEFAULT_PROBE_VERSION = "6.1.0-aurora-fake"
CAPABILITY_FULL = "full"
CAPABILITY_NO_LIBX265 = "no_libx265"
CAPABILITY_NO_TONEMAP = "no_tonemap"
PROBE_VERSION_ALT = "6.1.1-aurora-fake"


def create_fake_ffmpeg(
    dest: Path,
    *,
    profile: str = _DEFAULT_CAPABILITY,
    version: str = _DEFAULT_PROBE_VERSION,
) -> dict[str, Any]:
    """Write an executable fake ffmpeg and return its probe metadata."""
    if profile not in CAPABILITY_PROFILES:
        raise ValueError(f"unknown capability profile: {profile}")

    caps = CAPABILITY_PROFILES[profile]
    dest.parent.mkdir(parents=True, exist_ok=True)
    script = _FAKE_FFMPEG_TEMPLATE.format(
        profile_json=json.dumps(caps),
        version=version,
    )
    dest.write_text(script, encoding="utf-8")
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "executable": dest.name,
        "version_line": f"ffmpeg version {version} aurora-fake",
        "binary_digest": binary_digest(dest),
        "encoders": list(caps["encoders"]),
        "filters": list(caps["filters"]),
        "muxers": list(caps["muxers"]),
    }
