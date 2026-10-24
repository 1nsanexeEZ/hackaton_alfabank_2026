"""Компания по ИНН без заявки: что о ней говорят открытые источники и стоп-лист банка."""

from dataclasses import dataclass

from src.modules.enrichment.application.dto.bank import BankStopListDTO
from src.modules.enrichment.application.dto.counterparty import CounterpartyRiskDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import SourceErrorDTO
from src.modules.enrichment.application.dto.tax import TaxProfileDTO


@dataclass(frozen=True, slots=True)
class CompanyLookupDTO:
    """Выписка реестра есть всегда. ФНС, Контур и стоп-лист банка — `None`, если не ответили:
    тогда источник и причина — в `sources_failed`. БКИ здесь нет: без заявки нет и согласия."""

    registry: RegistryExtractDTO
    tax: TaxProfileDTO | None = None
    counterparty: CounterpartyRiskDTO | None = None
    bank_stop_list: BankStopListDTO | None = None
    sources_failed: tuple[SourceErrorDTO, ...] = ()
