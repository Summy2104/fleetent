"""In-memory pending link codes for manual IM identity attachment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass(frozen=True)
class PendingLink:
    code: str
    user_id: str
    tenant_id: str
    expires_at: datetime


class PendingLinkStore:
    def __init__(self, *, ttl: timedelta) -> None:
        self._ttl = ttl
        self._entries: dict[str, PendingLink] = {}
        self._lock = Lock()

    def put(self, code: str, *, user_id: str, tenant_id: str, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        entry = PendingLink(
            code=code,
            user_id=user_id,
            tenant_id=tenant_id,
            expires_at=current + self._ttl,
        )
        with self._lock:
            self._purge_expired_locked(current)
            self._entries[code] = entry

    def pop_valid(self, code: str, *, now: datetime | None = None) -> PendingLink | None:
        current = now or datetime.now(UTC)
        with self._lock:
            self._purge_expired_locked(current)
            entry = self._entries.pop(code, None)
            if entry is None or entry.expires_at <= current:
                return None
            return entry

    def _purge_expired_locked(self, now: datetime) -> None:
        expired = [code for code, entry in self._entries.items() if entry.expires_at <= now]
        for code in expired:
            self._entries.pop(code, None)
