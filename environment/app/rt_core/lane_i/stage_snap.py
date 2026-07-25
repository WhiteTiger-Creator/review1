from __future__ import annotations

from pathlib import Path

from rt_core.lane_g.snap_lane import freeze_view, load_rules
from rules_svc.book import RuleBook


_BOOK: RuleBook | None = None


def ensure_book() -> RuleBook:
    global _BOOK
    if _BOOK is None:
        _BOOK = RuleBook(Path("/app/config/rules-active.json"))
        load_rules(_BOOK)
    return _BOOK


def tenant_view(tenant: str) -> dict:
    ensure_book()
    return freeze_view(tenant)
