"""Refresh inventory content digests after media fixtures are generated at image build time."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

# Optional offline lab helpers (present when validation runners mount them).
try:
    import fake_ffmpeg as _lab_fake_ffmpeg
    import fixture_factory as _lab_fixture_factory
except ImportError:
    _lab_fake_ffmpeg = None
    _lab_fixture_factory = None


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_inventory(path: Path, assets_root: Path) -> None:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    for asset in inventory["assets"]:
        rel = asset["relative_path"]
        asset["content_digest"] = digest(assets_root / rel)
        for track in asset.get("subtitle_tracks", []):
            track_path = track.get("relative_path")
            if track_path:
                track["content_digest"] = digest(assets_root / track_path)
    path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("/data")
    assets = root / "assets"
    refresh_inventory(root / "cases/current/inventory.json", assets)
    refresh_inventory(root / "cases/legacy/inventory.json", assets)
    print("assets:", sorted(p.name for p in (assets / "clips").iterdir()))
    print("schema_tools:", jsonschema.__name__, yaml.__name__)
    print(
        "lab_helpers:",
        None if _lab_fake_ffmpeg is None else _lab_fake_ffmpeg.__name__,
        None if _lab_fixture_factory is None else _lab_fixture_factory.__name__,
    )


if __name__ == "__main__":
    main()
