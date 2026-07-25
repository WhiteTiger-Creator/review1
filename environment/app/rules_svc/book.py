from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path


class RuleBook:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.doc = json.loads(path.read_text(encoding="utf-8"))
        self.generation = int(self.doc.get("generation", 1))

    def tenant_view(self, tenant: str) -> dict:
        row = deepcopy(self.doc["tenants"][tenant])
        row["digest"] = hashlib.sha256(
            json.dumps(row, sort_keys=True).encode()
        ).hexdigest()[:16]
        row["generation"] = self.generation
        return row

    def active_generation(self) -> int:
        return self.generation
