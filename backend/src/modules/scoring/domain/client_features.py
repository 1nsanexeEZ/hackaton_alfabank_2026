"""Хранилище признаков клиента — «признаки из хранилища на дату заявки» общей схемы.

Вход скоринга делится на две группы:
- **признаки клиента** — то, что не зависит от заявки: возраст бизнеса и выручка (тренд), БКИ,
  недоимка, отрасль (ОКВЭД), сверка с реестром, прогноз по выписке, обороты в банке, какие
  источники не ответили. Их пишет обработчик `EnrichmentCompleted` на дату снимка;
- **признаки заявки** — сумма, срок, продукт, ставка, залог: из них модели считают сумму к
  выручке, долговую нагрузку с новым платежом и покрытие залогом.

`CalculateScore` берёт самый свежий снимок признаков клиента не старше `max_age_days` на дату
заявки; нет такого или данные обогащения этой заявки новее — считает из снимка обогащения и
сохраняет. Чистые функции: без IO и без `now()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)

# Версия набора признаков клиента: меняется состав — новая версия, старые снимки не трогаем.
CLIENT_FEATURES_VERSION = "client_features_v1"


@dataclass(frozen=True, slots=True)
class ClientFeatures:
    company: CompanyInput
    tax: TaxInput
    bureau: BureauInput
    cashflow: CashflowInput
    mass_address: bool
    sources_failed: tuple[str, ...]
    bank_months: int | None = None


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    id: UUID
    organization_id: UUID
    as_of: date  # дата, на которую собраны данные (дата снимка обогащения)
    collected_at: datetime  # когда собран снимок обогащения — чем новее, тем свежее признаки
    enrichment_snapshot_id: UUID
    features: ClientFeatures
    sources: tuple[str, ...]  # источники, ответившие в снимке
    version: str = CLIENT_FEATURES_VERSION


@dataclass(frozen=True, slots=True)
class FeatureStorePolicy:
    version: str
    max_age_days: int  # снимок признаков старше стольких дней на дату заявки не берём

    def oldest_as_of(self, application_date: date) -> date:
        return application_date - timedelta(days=self.max_age_days)

    def usable(self, stored: FeatureSnapshot | None, collected_at: datetime) -> bool:
        """Снимок из хранилища годится, если он не старее данных обогащения этой заявки."""
        return stored is not None and _utc(stored.collected_at) >= _utc(collected_at)


def _utc(moment: datetime) -> datetime:
    """Время без зоны (sqlite в тестах) считаем UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def client_features(inp: ScoringInput) -> ClientFeatures:
    return ClientFeatures(
        company=inp.company,
        tax=inp.tax,
        bureau=inp.bureau,
        cashflow=inp.cashflow,
        mass_address=inp.mass_address,
        sources_failed=inp.sources_failed,
        bank_months=inp.bank_months,
    )


def with_client_features(
    request: RequestInput, collateral: CollateralInput, as_of: date, client: ClientFeatures
) -> ScoringInput:
    """Вход скоринга: признаки заявки + признаки клиента из хранилища."""
    return ScoringInput(
        request=request,
        company=client.company,
        tax=client.tax,
        bureau=client.bureau,
        collateral=collateral,
        cashflow=client.cashflow,
        mass_address=client.mass_address,
        sources_failed=client.sources_failed,
        as_of=as_of,
        bank_months=client.bank_months,
    )
