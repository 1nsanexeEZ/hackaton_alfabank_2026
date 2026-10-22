from __future__ import annotations

from dataclasses import dataclass

from src.modules.enrichment.application.ports import (
    AccountingReportsSource,
    CounterpartyRiskSource,
    CreditBureauSource,
    PersonBureauSource,
    RegistrySource,
    TaxSource,
)


@dataclass(frozen=True)
class Sources:
    registry: RegistrySource
    tax: TaxSource
    bureau: CreditBureauSource
    accounting: AccountingReportsSource
    counterparty: CounterpartyRiskSource
    person_bureau: PersonBureauSource
