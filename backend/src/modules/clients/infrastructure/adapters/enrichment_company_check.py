"""The company by INN for the check before an application, through the enrichment facade:
its DTO become our value objects. On the stand enrichment asks external-mocks."""

from src.modules.clients.application.interfaces.company_check import CompanyCheckSource
from src.modules.clients.domain.enums import LegalForm
from src.modules.clients.domain.inn_check import (
    AccountBlock,
    BankruptcyNotice,
    CompanyRecord,
    CourtRecord,
    Founder,
    RegistryRecord,
    StopListRecord,
    TaxRecord,
)
from src.modules.clients.infrastructure.adapters.enrichment_registry import extract_of
from src.modules.enrichment.facade import (
    BankStopListDTO,
    CounterpartyRiskDTO,
    EnrichmentFacade,
    RegistryExtractDTO,
    TaxProfileDTO,
)


class EnrichmentCompanyCheck(CompanyCheckSource):
    def __init__(self, enrichment: EnrichmentFacade) -> None:
        self._enrichment = enrichment

    async def lookup(self, inn: str) -> CompanyRecord | None:
        company = await self._enrichment.lookup_company(inn)
        if company is None:
            return None
        return CompanyRecord(
            registry=_registry(company.registry),
            tax=_tax(company.tax) if company.tax is not None else None,
            court=_court(company.counterparty) if company.counterparty is not None else None,
            stop_list=(
                _stop_list(company.bank_stop_list) if company.bank_stop_list is not None else None
            ),
        )


def legal_form_of(dto: RegistryExtractDTO) -> LegalForm:
    """12 digits of the INN — an entrepreneur; АО, ПАО, НАО — a joint-stock company."""
    if len(dto.inn) == 12:
        return LegalForm.IE
    return LegalForm.JSC if dto.legal_form.strip().upper().endswith("АО") else LegalForm.LLC


def _registry(dto: RegistryExtractDTO) -> RegistryRecord:
    """InfrastructureError (`bad_registry_data`) if the value objects do not accept the extract."""
    return RegistryRecord(
        extract=extract_of(dto),
        legal_form=legal_form_of(dto),
        full_name=dto.full_name,
        registered_at=dto.registered_at,
        head_position=dto.head_position,
        head_since=dto.head_since,
        mass_address=dto.mass_address,
        unreliable=dto.unreliable,
        founders=tuple(Founder(f.name, f.share_percent, f.inn) for f in dto.founders),
    )


def _tax(dto: TaxProfileDTO) -> TaxRecord:
    return TaxRecord(
        tax_regime=dto.tax_regime,
        avg_headcount=dto.avg_headcount,
        reported_revenue=dto.reported_revenue,
        report_year=dto.report_year,
        tax_arrears=dto.tax_arrears,
        in_msp_registry=dto.in_msp_registry,
        disqualified_head=dto.disqualified_head,
        mass_head=dto.mass_head,
        account_blocks=tuple(
            AccountBlock(b.decision_number, b.date, b.reason) for b in dto.account_blocks
        ),
    )


def _court(dto: CounterpartyRiskDTO) -> CourtRecord:
    return CourtRecord(
        reliability=dto.reliability,
        notes=dto.notes,
        arbitration_as_defendant=dto.arbitration.as_defendant,
        arbitration_defendant_sum=dto.arbitration.defendant_sum,
        enforcement_active=dto.enforcement.active,
        enforcement_sum=dto.enforcement.sum,
        bankruptcy=tuple(BankruptcyNotice(m.date, m.type, m.case) for m in dto.bankruptcy_messages),
    )


def _stop_list(dto: BankStopListDTO) -> StopListRecord:
    return StopListRecord(listed=dto.listed, reason=dto.reason)
