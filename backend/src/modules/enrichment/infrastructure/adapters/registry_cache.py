"""Кеш просмотров реестра в памяти процесса: запись живёт `ttl`."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.core.domain.clock import Clock, SystemClock
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.interfaces.registry_cache import RegistryCache

_LOOKUP_TTL = timedelta(minutes=10)


class InMemoryRegistryCache(RegistryCache):
    def __init__(self, *, ttl: timedelta = _LOOKUP_TTL, clock: Clock | None = None) -> None:
        self._ttl = ttl
        self._clock = clock or SystemClock()
        self._entries: dict[str, tuple[datetime, RegistryExtractDTO]] = {}

    def get(self, inn: str) -> RegistryExtractDTO | None:
        entry = self._entries.get(inn)
        if entry is None or entry[0] <= self._clock.now():
            return None
        return entry[1]

    def put(self, inn: str, extract: RegistryExtractDTO) -> None:
        self._entries[inn] = (self._clock.now() + self._ttl, extract)
