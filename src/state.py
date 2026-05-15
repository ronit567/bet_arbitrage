"""In-memory dedupe so the same arb doesn't alert on every poll cycle."""
from __future__ import annotations

import time

from .models import ArbOpportunity


class AlertedState:
    """Remembers arb dedupe keys with a TTL so stale entries expire."""

    def __init__(self, ttl_seconds: int = 600):
        self._seen: dict[str, float] = {}
        self._ttl = ttl_seconds

    def _gc(self) -> None:
        now = time.time()
        expired = [k for k, t in self._seen.items() if now - t > self._ttl]
        for k in expired:
            del self._seen[k]

    def is_new(self, arb: ArbOpportunity) -> bool:
        self._gc()
        return arb.dedupe_key() not in self._seen

    def mark(self, arb: ArbOpportunity) -> None:
        self._seen[arb.dedupe_key()] = time.time()
