"""Stage JSON persistence."""
from __future__ import annotations

import json
from pathlib import Path


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return obj


def reload_json(_path, fallback):
    return fallback
