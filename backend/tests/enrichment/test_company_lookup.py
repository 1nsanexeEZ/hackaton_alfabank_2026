"""EnrichmentFacade.lookup_company: the company before any application — the registry past
the cache, the tax service, Kontur and the bank stop list; a source that fails is named."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.application.use_cases.lookup_company import LookupCompanyUseCase
from src.modules.enrichment.application.use_cases.lookup_registry import LookupRegistryUseCase
from src.modules.enrichment.facade import BankStopListDTO, SourceErrorDTO
from src.modules.enrichment.infrastructure.adapters.bank_stop_list_http import (
    BankStopListHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource
from src.modules.enrichment.infrastructure.adapters.kontur_http import KonturHttpSource
from src.modules.enrichment.infrastructure.adapters.registry_cache import InMemoryRegistryCache
from tests.enrichment.fixtures import ROMASHKA_EGRUL, ROMASHKA_FNS, ZAKAT_KONTUR

INN = "7701158817"
STOP_LIST = {"inn": INN, "listed": False, "reason": None, "listed_at": None}


class _Mocks:
    """external-mocks by path; `down` — paths that answer 503."""

    def __init__(self, *down: str) -> None:
        self.down = set(down)
        self.paths: list[str] = []
        self.answers = {
            f"/egrul/{INN}": ROMASHKA_EGRUL,
            f"/fns/{INN}": ROMASHKA_FNS,
            f"/kontur/{INN}": ZAKAT_KONTUR,
            f"/abs/stop-list/{INN}": STOP_LIST,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if path.rsplit("/", 1)[0] in self.down:
            return httpx.Response(503)
        if path in self.answers:
            return httpx.Response(200, json=self.answers[path])
        return httpx.Response(404, json={"detail": "nf"})

    def lookup(self, cache: InMemoryRegistryCache | None = None) -> LookupCompanyUseCase:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler), base_url="http://m")
        unused = object()
        sources = Sources(
            registry=EgrulHttpSource(client, backoff=()),
            tax=FnsHttpSource(client, backoff=()),
            bureau=unused,  # type: ignore[arg-type]
            accounting=unused,  # type: ignore[arg-type]
            counterparty=KonturHttpSource(client, backoff=()),
            person_bureau=unused,  # type: ignore[arg-type]
            aml_lists=unused,  # type: ignore[arg-type]
            pep=unused,  # type: ignore[arg-type]
            zsk=unused,  # type: ignore[arg-type]
            bank_stop_list=BankStopListHttpSource(client, backoff=()),
            bank_turnover=unused,  # type: ignore[arg-type]
        )
        registry = LookupRegistryUseCase(sources.registry, cache or InMemoryRegistryCache())
        return LookupCompanyUseCase(registry, sources)


async def test_all_sources_answer() -> None:
    mocks = _Mocks()
    cache = InMemoryRegistryCache()

    company = await mocks.lookup(cache).execute(INN)

    assert company is not None
    assert company.registry.inn == INN and company.registry.kpp == "770101001"
    assert company.tax is not None and company.tax.tax_arrears == Decimal(0)
    assert company.counterparty is not None and company.counterparty.enforcement.active == 4
    assert company.bank_stop_list == BankStopListDTO(listed=False)
    assert company.sources_failed == ()
    # The registry is asked past the cache and refreshes it, as the check on request does.
    assert cache.get(INN) == company.registry


async def test_failed_source_is_named_and_the_rest_are_kept() -> None:
    company = await _Mocks("/fns", "/abs/stop-list").lookup().execute(INN)

    assert company is not None
    assert company.tax is None and company.bank_stop_list is None
    assert company.counterparty is not None
    assert [(e.source, e.code) for e in company.sources_failed] == [
        ("fns", "unavailable"),
        ("bank_stop_list", "unavailable"),
    ]
    assert all(isinstance(e, SourceErrorDTO) and e.message for e in company.sources_failed)


async def test_unknown_inn_asks_nobody_else() -> None:
    mocks = _Mocks()

    assert await mocks.lookup().execute("7702987976") is None
    assert mocks.paths == ["/egrul/7702987976"]


async def test_registry_down_is_an_infrastructure_error() -> None:
    mocks = _Mocks("/egrul")

    with pytest.raises(InfrastructureError):
        await mocks.lookup().execute(INN)
    assert mocks.paths == [f"/egrul/{INN}"]
