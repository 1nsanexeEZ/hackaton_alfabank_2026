"""BusinessPlan — the project of a startup before its application: what the business does and
its financial model by the bank's template.

One plan per company: submitted again, it is revised. The bank assesses it (decision through
scoring) and pre-approves a startup loan up to what the project carries; the figures here are
what the client declares, the bank does not change them.

The template of the financial model: revenue and operating expenses for each of the first
24 months, own funds put into the project, collateral, a state support guarantee and the loan
the project needs.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError

HORIZON_MONTHS = 24
SUMMARY_MAX_LENGTH = 4000
COLLATERAL_MAX_LENGTH = 500


def _invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


class StateGuarantee(StrEnum):
    """Who guarantees a part of the loan under state support."""

    NONE = "none"
    MSP_CORPORATION = "msp_corporation"  # Корпорация МСП
    REGIONAL_FUND = "regional_fund"  # региональная гарантийная организация


@dataclass(frozen=True, slots=True)
class PlanMonth:
    revenue: Money
    expenses: Money  # operating, without payments on the loan asked for


@dataclass(frozen=True, slots=True)
class FinancialModel:
    months: tuple[PlanMonth, ...]
    own_funds: Money
    collateral_value: Money  # 0 — no collateral
    collateral_description: str | None
    guarantee: StateGuarantee
    guarantee_share: Decimal  # share of the loan under the guarantee; 0 without one
    loan_amount: Money
    loan_term_months: int

    def __post_init__(self) -> None:
        if len(self.months) != HORIZON_MONTHS:
            raise _invalid("months", "horizon", f"The model covers exactly {HORIZON_MONTHS} months")
        currency = self.loan_amount.currency
        amounts = {
            "own_funds": self.own_funds,
            "collateral_value": self.collateral_value,
            "loan_amount": self.loan_amount,
        }
        for month in self.months:
            for money in (month.revenue, month.expenses):
                if money.currency != currency:
                    raise _invalid("months", "currency_mismatch", "All figures in one currency")
                if money.is_negative:
                    raise _invalid("months", "negative", "Value must not be negative")
        for name, money in amounts.items():
            if money.currency != currency:
                raise _invalid(name, "currency_mismatch", "All figures must be in one currency")
            if money.is_negative:
                raise _invalid(name, "negative", "Value must not be negative")
        if self.loan_amount.amount <= 0:
            raise _invalid("loan_amount", "not_positive", "The loan amount must be positive")
        if self.loan_term_months <= 0:
            raise _invalid("loan_term_months", "not_positive", "The term must be positive")
        if self.guarantee is StateGuarantee.NONE:
            if self.guarantee_share != 0:
                raise _invalid(
                    "guarantee_share", "no_guarantee", "No guarantee — no guaranteed share"
                )
        elif not 0 < self.guarantee_share <= 1:
            raise _invalid(
                "guarantee_share", "out_of_range", "The guaranteed share is above 0 and up to 1"
            )
        description = self.collateral_description
        if description is not None and len(description) > COLLATERAL_MAX_LENGTH:
            raise _invalid("collateral_description", "too_long", "The description is too long")


class BusinessPlan:
    def __init__(
        self,
        *,
        organization_id: UUID,
        summary: str,
        model: FinancialModel,
        submitted_by: UUID | None,
        submitted_at: datetime,
        revision: int = 1,
    ) -> None:
        self.organization_id = organization_id
        self.summary = summary
        self.model = model
        self.submitted_by = submitted_by
        self.submitted_at = submitted_at
        self.revision = revision

    @classmethod
    def submit(
        cls,
        *,
        organization_id: UUID,
        summary: str,
        model: FinancialModel,
        submitted_by: UUID | None,
        now: datetime,
    ) -> Self:
        """Rights are checked by the caller: `edit_financials` in the company."""
        return cls(
            organization_id=organization_id,
            summary=_summary(summary),
            model=model,
            submitted_by=submitted_by,
            submitted_at=now,
        )

    def revise(
        self, summary: str, model: FinancialModel, submitted_by: UUID | None, now: datetime
    ) -> None:
        self.summary = _summary(summary)
        self.model = model
        self.submitted_by = submitted_by
        self.submitted_at = now
        self.revision += 1


def _summary(summary: str) -> str:
    text = summary.strip()
    if not text:
        raise _invalid("summary", "empty", "Describe the project")
    if len(text) > SUMMARY_MAX_LENGTH:
        raise _invalid("summary", "too_long", "The description is too long")
    return text
