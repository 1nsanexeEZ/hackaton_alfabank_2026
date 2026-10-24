"""Enrichment contract: what external sources and bank statements said about
the company at the time of the application.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.enrichment.application.dto.accounting import (
    AccountingPeriodDTO,
    AccountingReportsDTO,
)
from src.modules.enrichment.application.dto.aml import (
    AmlCheckDTO,
    AmlSubjectDTO,
    BeneficialOwnerDTO,
    ListHitDTO,
    PepHitDTO,
    ZskRiskDTO,
)
from src.modules.enrichment.application.dto.bank import (
    BankStopListDTO,
    BankTurnoverDTO,
    TurnoverMonthDTO,
)
from src.modules.enrichment.application.dto.cashflow import (
    CashflowForecastDTO,
    CashflowMonthDTO,
    CashflowProjectionDTO,
)
from src.modules.enrichment.application.dto.counterparty import (
    ArbitrationDTO,
    BankruptcyMessageDTO,
    CounterpartyRiskDTO,
    EnforcementDTO,
    GovContractsDTO,
)
from src.modules.enrichment.application.dto.credit_history import (
    CreditHistoryDTO,
    ObligationDTO,
    PersonDTO,
)
from src.modules.enrichment.application.dto.registry import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import EnrichmentSnapshotDTO, SourceErrorDTO
from src.modules.enrichment.application.dto.tax import AccountBlockDTO, TaxProfileDTO
from src.modules.enrichment.domain.enums import Source

__all__ = [
    "AccountBlockDTO",
    "AmlCheckDTO",
    "AmlSubjectDTO",
    "BeneficialOwnerDTO",
    "ListHitDTO",
    "PepHitDTO",
    "ZskRiskDTO",
    "AccountingPeriodDTO",
    "AccountingReportsDTO",
    "ArbitrationDTO",
    "BankStopListDTO",
    "BankTurnoverDTO",
    "BankruptcyMessageDTO",
    "CashflowForecastDTO",
    "CashflowMonthDTO",
    "CashflowProjectionDTO",
    "CounterpartyRiskDTO",
    "CreditHistoryDTO",
    "EnforcementDTO",
    "EnrichmentFacade",
    "EnrichmentSnapshotDTO",
    "FounderDTO",
    "GovContractsDTO",
    "ObligationDTO",
    "PersonDTO",
    "RegistryExtractDTO",
    "Source",
    "SourceErrorDTO",
    "TaxProfileDTO",
    "TurnoverMonthDTO",
]


class EnrichmentFacade(Protocol):
    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None: ...

    async def latest_cashflow(self, organization_id: UUID) -> CashflowForecastDTO | None:
        """The latest cash flow forecast of the company, from a bank statement in any of
        its recent applications. None — no statement yet: a cash gap is unknown."""
        ...

    async def lookup_registry(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        """None — the registry does not know the INN; InfrastructureError — it
        did not answer. `fresh` — past the cache (a check on request)."""
        ...

    async def lookup_person_bureau(
        self, person: PersonDTO, consent_at: datetime
    ) -> CreditHistoryDTO | None:
        """The person's credit history right away, without an application (the
        founder's prescreen); only with their consent given at `consent_at`.
        None — the bureau does not know them; InfrastructureError — it did not answer."""
        ...
