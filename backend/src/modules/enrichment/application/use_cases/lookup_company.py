"""Компания по ИНН без заявки (проверка до заявки в clients): реестр, ФНС, Контур и стоп-лист
банка. Согласия не нужны: это открытые сведения и собственные данные банка."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.modules.enrichment.application.dto.company import CompanyLookupDTO
from src.modules.enrichment.application.dto.snapshot import SourceErrorDTO
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.application.use_cases.lookup_registry import LookupRegistryUseCase
from src.modules.enrichment.domain.enums import Source
from src.modules.enrichment.domain.exceptions import SourceFetchError


class LookupCompanyUseCase:
    def __init__(self, registry: LookupRegistryUseCase, sources: Sources) -> None:
        self._registry = registry
        self._sources = sources

    async def execute(self, inn: str) -> CompanyLookupDTO | None:
        """Реестр — мимо кеша, как при сверке по запросу. None — реестр не знает ИНН (остальных
        не спрашиваем); InfrastructureError — реестр не ответил. Остальные источники — параллельно,
        сбой одного не мешает другим."""
        extract = await self._registry.execute(inn, fresh=True)
        if extract is None:
            return None
        (
            (tax, tax_error),
            (counterparty, counterparty_error),
            (stop_list, stop_error),
        ) = await asyncio.gather(
            _optional("fns", lambda: self._sources.tax.fetch(inn)),
            _optional("kontur", lambda: self._sources.counterparty.fetch(inn)),
            _optional("bank_stop_list", lambda: self._sources.bank_stop_list.fetch(inn)),
        )
        return CompanyLookupDTO(
            registry=extract,
            tax=tax,
            counterparty=counterparty,
            bank_stop_list=stop_list,
            sources_failed=tuple(
                error for error in (tax_error, counterparty_error, stop_error) if error is not None
            ),
        )


async def _optional[T](
    source: Source, fetch: Callable[[], Awaitable[T]]
) -> tuple[T | None, SourceErrorDTO | None]:
    try:
        return await fetch(), None
    except SourceFetchError as exc:
        return None, SourceErrorDTO(source=source, code=exc.kind, message=str(exc))
