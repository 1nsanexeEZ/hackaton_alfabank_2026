"""Сборка доменного `ScoringInput` из того, что отдают соседи: заявка и снимок компании —
`applications.get_scoring_input`; источники и прогноз по выписке — `enrichment.get_snapshot`.

Здесь граница: DTO соседей переводятся в доменный вход так, чтобы домен не знал про фасады.
`as_of = submitted_at` — чтобы расчёт был воспроизводим.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.modules.applications.facade import ScoringInputDTO
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)


def build_scoring_input(
    application: ScoringInputDTO, snapshot: EnrichmentSnapshotDTO
) -> ScoringInput:
    organization = application.organization
    reports = organization.financial_reports
    fns = snapshot.fns
    bki = snapshot.bki
    cashflow = snapshot.cashflow

    return ScoringInput(
        request=RequestInput(
            amount=application.request.amount,
            term_months=application.request.term_months,
            product_code=application.product_code,
            facility=application.product_terms.facility,
            rate_base=application.product_terms.rate_base,
        ),
        company=CompanyInput(
            legal_form=organization.legal_form,
            business_age_months=organization.business_age_months,
            okved_main=organization.okved_main,
            verification_status=organization.verification_status,
            registry_status=organization.registry_status,
            declared_revenue=reports[0].revenue if reports else None,
            declared_revenue_previous=reports[1].revenue if len(reports) > 1 else None,
            monthly_debt_payments_declared=(reports[0].monthly_debt_payments if reports else None),
        ),
        tax=TaxInput(
            tax_arrears=fns.tax_arrears if fns is not None else None,
            reported_revenue=fns.reported_revenue if fns is not None else None,
        ),
        bureau=BureauInput(
            available=bki is not None,
            has_history=bki is not None and len(bki.obligations) > 0,
            max_overdue_days_12m=bki.max_overdue_days_12m if bki is not None else None,
            inquiries_last_30d=bki.inquiries_last_30d if bki is not None else None,
            total_monthly_payments=(bki.total_monthly_payments if bki is not None else Decimal(0)),
        ),
        collateral=CollateralInput(
            declared_value=application.collateral.declared_value
            if application.collateral is not None
            else None
        ),
        cashflow=CashflowInput(
            present=cashflow is not None,
            gap_detected=cashflow.gap_detected if cashflow is not None else None,
            gap_month=cashflow.gap_month if cashflow is not None else None,
            gap_amount=cashflow.gap_amount if cashflow is not None else None,
            revenue_confirmed=cashflow.revenue_confirmed if cashflow is not None else None,
        ),
        mass_address=snapshot.egrul.mass_address if snapshot.egrul is not None else False,
        sources_failed=tuple(error.source for error in snapshot.sources_failed),
        as_of=application.submitted_at.date(),
        bank_months=_bank_months(snapshot, application.submitted_at.date()),
    )


def _bank_months(snapshot: EnrichmentSnapshotDTO, as_of: date) -> int | None:
    """Полных месяцев оборотов в банке до даты заявки: не клиент банка — 0, АБС не ответила —
    None (сегмент тогда по возрасту бизнеса)."""
    turnover = snapshot.bank_turnover
    if turnover is None:
        return None
    since = turnover.client_since
    if since is None or since > as_of:
        return 0
    months = (as_of.year - since.year) * 12 + as_of.month - since.month
    return max(months - (1 if as_of.day < since.day else 0), 0)
