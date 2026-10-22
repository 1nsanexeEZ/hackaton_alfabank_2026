"""Канонический снимок входа и его хеш — основа воспроизводимости.

`input_snapshot` хранится как есть; `input_hash` = sha256 канонического JSON. По снимку и версии
модели расчёт повторяется бит в бит (Replay). Суммы — строками, даты — ISO; чистый stdlib.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)


def dump_input(inp: ScoringInput) -> dict[str, Any]:
    return {
        "request": {
            "amount": _dec(inp.request.amount),
            "term_months": inp.request.term_months,
            "product_code": inp.request.product_code,
            "facility": inp.request.facility,
            "rate_base": _dec(inp.request.rate_base),
        },
        "company": {
            "legal_form": inp.company.legal_form,
            "business_age_months": inp.company.business_age_months,
            "okved_main": inp.company.okved_main,
            "verification_status": inp.company.verification_status,
            "registry_status": inp.company.registry_status,
            "declared_revenue": _dec(inp.company.declared_revenue),
            "declared_revenue_previous": _dec(inp.company.declared_revenue_previous),
            "monthly_debt_payments_declared": _dec(inp.company.monthly_debt_payments_declared),
        },
        "tax": {
            "tax_arrears": _dec(inp.tax.tax_arrears),
            "reported_revenue": _dec(inp.tax.reported_revenue),
        },
        "bureau": {
            "available": inp.bureau.available,
            "has_history": inp.bureau.has_history,
            "max_overdue_days_12m": inp.bureau.max_overdue_days_12m,
            "inquiries_last_30d": inp.bureau.inquiries_last_30d,
            "total_monthly_payments": _dec(inp.bureau.total_monthly_payments),
        },
        "collateral": {"declared_value": _dec(inp.collateral.declared_value)},
        "cashflow": {
            "present": inp.cashflow.present,
            "gap_detected": inp.cashflow.gap_detected,
            "gap_month": inp.cashflow.gap_month,
            "gap_amount": _dec(inp.cashflow.gap_amount),
            "revenue_confirmed": inp.cashflow.revenue_confirmed,
        },
        "mass_address": inp.mass_address,
        "sources_failed": list(inp.sources_failed),
        "as_of": inp.as_of.isoformat(),
    }


def load_input(raw: dict[str, Any]) -> ScoringInput:
    request, company, tax = raw["request"], raw["company"], raw["tax"]
    bureau, collateral, cashflow = raw["bureau"], raw["collateral"], raw["cashflow"]
    return ScoringInput(
        request=RequestInput(
            amount=Decimal(request["amount"]),
            term_months=request["term_months"],
            product_code=request["product_code"],
            facility=request["facility"],
            rate_base=Decimal(request["rate_base"]),
        ),
        company=CompanyInput(
            legal_form=company["legal_form"],
            business_age_months=company["business_age_months"],
            okved_main=company["okved_main"],
            verification_status=company["verification_status"],
            registry_status=company["registry_status"],
            declared_revenue=_num(company["declared_revenue"]),
            declared_revenue_previous=_num(company["declared_revenue_previous"]),
            monthly_debt_payments_declared=_num(company["monthly_debt_payments_declared"]),
        ),
        tax=TaxInput(
            tax_arrears=_num(tax["tax_arrears"]),
            reported_revenue=_num(tax["reported_revenue"]),
        ),
        bureau=BureauInput(
            available=bureau["available"],
            has_history=bureau["has_history"],
            max_overdue_days_12m=bureau["max_overdue_days_12m"],
            inquiries_last_30d=bureau["inquiries_last_30d"],
            total_monthly_payments=Decimal(bureau["total_monthly_payments"]),
        ),
        collateral=CollateralInput(declared_value=_num(collateral["declared_value"])),
        cashflow=CashflowInput(
            present=cashflow["present"],
            gap_detected=cashflow["gap_detected"],
            gap_month=cashflow["gap_month"],
            gap_amount=_num(cashflow["gap_amount"]),
            revenue_confirmed=cashflow["revenue_confirmed"],
        ),
        mass_address=raw["mass_address"],
        sources_failed=tuple(raw["sources_failed"]),
        as_of=date.fromisoformat(raw["as_of"]),
    )


def input_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dec(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _num(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None
