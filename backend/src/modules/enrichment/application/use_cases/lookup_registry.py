"""Разовый просмотр реестра по ИНН (сверка компании) — через кеш."""

from __future__ import annotations

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.interfaces.registry_cache import RegistryCache
from src.modules.enrichment.application.interfaces.sources import RegistrySource
from src.modules.enrichment.domain.exceptions import SourceNotFound, SourceUnavailable


class LookupRegistryUseCase:
    def __init__(self, registry: RegistrySource, cache: RegistryCache) -> None:
        self._registry = registry
        self._cache = cache

    async def execute(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        """None — реестр не знает ИНН; InfrastructureError — он не ответил.
        `fresh` — мимо кеша (проверка по запросу)."""
        if not fresh and (cached := self._cache.get(inn)) is not None:
            return cached
        try:
            extract = await self._registry.fetch(inn)
        except SourceNotFound:
            return None
        except SourceUnavailable as exc:
            raise InfrastructureError("Реестр временно недоступен") from exc
        self._cache.put(inn, extract)
        return extract
