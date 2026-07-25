from __future__ import annotations

import json
from pathlib import Path

from rules_svc.book import RuleBook


def commit_rules(book: RuleBook, candidate: Path) -> int:
    new_doc = json.loads(candidate.read_text(encoding="utf-8"))
    book.doc["tenants"].update(new_doc.get("tenants", {}))
    book.generation = int(new_doc.get("generation", book.generation + 1))
    book.path.write_text(json.dumps(book.doc, indent=2) + "\n", encoding="utf-8")
    return book.generation
