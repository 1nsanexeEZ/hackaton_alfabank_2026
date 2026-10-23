"""EnrichmentFacade.lookup_registry: the cache and the check on request past it."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.use_cases.lookup_registry import LookupRegistryUseCase
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.registry_cache import InMemoryRegistryCache
from tests.enrichment.fixtures import ROMASHKA_EGRUL

INN = "7701158817"


class _Registry:
    def __init__(self, status: int = 200) -> None:
        self.calls = 0
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.status != 200:
            return httpx.Response(self.status)
        if request.url.path == f"/egrul/{INN}":
            return httpx.Response(200, json=ROMASHKA_EGRUL)
        return httpx.Response(404, json={"detail": "nf"})

    def source(self) -> EgrulHttpSource:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler), base_url="http://m")
        return EgrulHttpSource(client, backoff=())


def _lookup(
    registry: _Registry, cache: InMemoryRegistryCache | None = None
) -> LookupRegistryUseCase:
    return LookupRegistryUseCase(registry.source(), cache or InMemoryRegistryCache())


async def test_lookup_is_cached_and_fresh_goes_past_the_cache() -> None:
    registry = _Registry()
    lookup = _lookup(registry)

    first = await lookup.execute(INN)
    again = await lookup.execute(INN)
    assert registry.calls == 1 and first == again

    fresh = await lookup.execute(INN, fresh=True)
    assert registry.calls == 2
    assert fresh is not None and fresh.kpp == "770101001"


async def test_cached_lookup_expires() -> None:
    registry, clock = _Registry(), FrozenClock()
    lookup = _lookup(registry, InMemoryRegistryCache(ttl=timedelta(minutes=10), clock=clock))

    await lookup.execute(INN)
    clock.advance(timedelta(minutes=9))
    await lookup.execute(INN)
    assert registry.calls == 1

    clock.advance(timedelta(minutes=1))
    await lookup.execute(INN)
    assert registry.calls == 2


async def test_unknown_inn_and_unavailable_registry() -> None:
    assert await _lookup(_Registry()).execute("7702987976", fresh=True) is None
    with pytest.raises(InfrastructureError):
        await _lookup(_Registry(status=503)).execute(INN, fresh=True)
