"""EnrichmentFacade.lookup_registry: the cache and the check on request past it."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.infrastructure import facade_impl
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.facade_impl import EnrichmentFacadeImpl
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


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(facade_impl, "_lookup_cache", {})


async def test_lookup_is_cached_and_fresh_goes_past_the_cache(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _Registry()
    async with session_factory() as session:
        facade = EnrichmentFacadeImpl(session, registry.source())

        first = await facade.lookup_registry(INN)
        again = await facade.lookup_registry(INN)
        assert registry.calls == 1 and first == again

        fresh = await facade.lookup_registry(INN, fresh=True)
        assert registry.calls == 2
        assert fresh is not None and fresh.kpp == "770101001"


async def test_unknown_inn_and_unavailable_registry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        assert (
            await EnrichmentFacadeImpl(session, _Registry().source()).lookup_registry(
                "7702987976", fresh=True
            )
            is None
        )
        down = EnrichmentFacadeImpl(session, _Registry(status=503).source())
        with pytest.raises(InfrastructureError):
            await down.lookup_registry(INN, fresh=True)
