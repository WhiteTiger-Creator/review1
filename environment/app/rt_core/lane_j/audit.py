from __future__ import annotations

import json
from pathlib import Path

AUDIT = Path("/var/log/rt-daemon/audit.log")


def write_audit(doc: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "tenant": doc.get("tenant"),
        "module_digest": doc.get("module_digest"),
        "policy_digest": doc.get("policy_digest"),
        "cache": doc.get("cache"),
        "effective_caps": doc.get("effective_caps"),
        "result_status": doc.get("result", {}).get("status"),
    }
    with AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
