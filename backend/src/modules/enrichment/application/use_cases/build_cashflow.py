"""Сборка прогноза кассового разрыва: читает выписки и параметры заявки через фасад
applications, считает оценочный платёж по новому кредиту и зовёт доменный прогноз.
"""

from __future__ import annotations

from decimal import Decimal

from src.core.messaging.contracts.enrichment import FetchEnrichment
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.application.dto.cashflow import (
    CashflowForecastDTO,
    CashflowMonthDTO,
    CashflowProjectionDTO,
)
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO
from src.modules.enrichment.application.interfaces.statement_parser import StatementParser
from src.modules.enrichment.domain.cashflow import CashflowForecast, Transaction, build_forecast

_CENT = Decimal("0.01")


class CashflowBuilder:
    def __init__(self, applications: ApplicationsFacade, parser: StatementParser) -> None:
        self._applications = applications
        self._parser = parser

    async def build(
        self, command: FetchEnrichment, bki: CreditHistoryDTO | None
    ) -> CashflowForecastDTO | None:
        if not command.statement_document_ids:
            return None
        scoring_input = await self._applications.get_scoring_input(command.application_id)
        transactions: list[Transaction] = []
        for document_id in command.statement_document_ids:
            content = await self._applications.read_document(command.application_id, document_id)
            transactions.extend(self._parser.parse(content))
        if not transactions:
            return None
        reports = scoring_input.organization.financial_reports
        forecast = build_forecast(
            transactions,
            current_monthly_payments=bki.total_monthly_payments if bki is not None else Decimal(0),
            new_loan_payment=_annuity(
                scoring_input.request.amount,
                scoring_input.request.term_months,
                scoring_input.product_terms.rate_base,
            ),
            declared_annual_revenue=reports[0].revenue if reports else None,
            as_of=scoring_input.submitted_at.date(),
            statement_document_ids=tuple(command.statement_document_ids),
        )
        return to_dto(forecast)


def to_dto(forecast: CashflowForecast) -> CashflowForecastDTO:
    return CashflowForecastDTO(
        months_history=tuple(
            CashflowMonthDTO(
                month=m.month, inflow=m.inflow, outflow=m.outflow, net=m.net, balance=m.balance
            )
            for m in forecast.months_history
        ),
        forecast=tuple(
            CashflowProjectionDTO(month=p.month, projected_balance=p.projected_balance)
            for p in forecast.forecast
        ),
        gap_detected=forecast.gap_detected,
        gap_month=forecast.gap_month,
        gap_amount=forecast.gap_amount,
        annual_inflow=forecast.annual_inflow,
        revenue_confirmed=forecast.revenue_confirmed,
        method=forecast.method,
        statement_document_ids=forecast.statement_document_ids,
    )


def _annuity(amount: Decimal, term_months: int, annual_rate_percent: Decimal) -> Decimal:
    """Оценочный аннуитетный платёж по новому кредиту — консервативная нагрузка, не решение."""
    if term_months <= 0:
        return amount
    monthly_rate = annual_rate_percent / Decimal(100) / Decimal(12)
    if monthly_rate == 0:
        return (amount / term_months).quantize(_CENT)
    factor = (1 + monthly_rate) ** term_months
    return (amount * monthly_rate * factor / (factor - 1)).quantize(_CENT)
