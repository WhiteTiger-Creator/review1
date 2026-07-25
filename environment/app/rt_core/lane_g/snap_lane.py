from __future__ import annotations

from rules_svc.book import RuleBook


_BOOK: RuleBook | None = None


def load_rules(book: RuleBook) -> None:
    global _BOOK
    _BOOK = book


def freeze_view(tenant: str) -> dict:
    if _BOOK is None:
        raise RuntimeError("policy-unavailable")
    return _BOOK.tenant_view(tenant)
