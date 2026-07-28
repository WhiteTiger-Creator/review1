from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def wtac_load_campaign(campaign_dir: Path) -> dict[str, Any]:
    root = Path(campaign_dir)
    out: dict[str, Any] = {}
    for name in ("conditions", "geometry", "pressures", "balance", "tare_runs"):
        path = root / f"{name}.json"
        out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out
