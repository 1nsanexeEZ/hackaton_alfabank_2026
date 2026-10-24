"""Канонический снимок входа и его хеш — основа воспроизводимости.

`input_snapshot` хранится как есть; `input_hash` = sha256 канонического JSON. По снимку и версии
модели расчёт повторяется бит в бит (Replay). Суммы — строками, даты — ISO; чистый stdlib.
Признаки клиента в хранилище (`scoring_feature_snapshots.features`) — в том же формате.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from src.modules.scoring.domain.client_features import (
    ClientFeatures,
    client_features,
    with_client_features,
)
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
    """Признаки заявки (request, collateral, as_of) и признаки клиента — плоско, как всегда."""
    return {
        "request": {
            "amount": _dec(inp.request.amount),
            "term_months": inp.request.term_months,
            "product_code": inp.request.product_code,
            "facility": inp.request.facility,
            "rate_base": _dec(inp.request.rate_base),
        },
        "collateral": {"declared_value": _dec(inp.collateral.declared_value)},
        "as_of": inp.as_of.isoformat(),
        **dump_client_features(client_features(inp)),
    }


def load_input(raw: dict[str, Any]) -> ScoringInput:
    request, collateral = raw["request"], raw["collateral"]
    return with_client_features(
        RequestInput(
            amount=Decimal(request["amount"]),
            term_months=request["term_months"],
            product_code=request["product_code"],
            facility=request["facility"],
            rate_base=Decimal(request["rate_base"]),
        ),
        CollateralInput(declared_value=_num(collateral["declared_value"])),
        date.fromisoformat(raw["as_of"]),
        load_client_features(raw),
    )


def dump_client_features(features: ClientFeatures) -> dict[str, Any]:
    return {
        "company": {
            "legal_form": features.company.legal_form,
            "business_age_months": features.company.business_age_months,
            "okved_main": features.company.okved_main,
            "verification_status": features.company.verification_status,
            "registry_status": features.company.registry_status,
            "declared_revenue": _dec(features.company.declared_revenue),
            "declared_revenue_previous": _dec(features.company.declared_revenue_previous),
            "monthly_debt_payments_declared": _dec(features.company.monthly_debt_payments_declared),
        },
        "tax": {
            "tax_arrears": _dec(features.tax.tax_arrears),
            "reported_revenue": _dec(features.tax.reported_revenue),
        },
        "bureau": {
            "available": features.bureau.available,
            "has_history": features.bureau.has_history,
            "max_overdue_days_12m": features.bureau.max_overdue_days_12m,
            "inquiries_last_30d": features.bureau.inquiries_last_30d,
            "total_monthly_payments": _dec(features.bureau.total_monthly_payments),
        },
        "cashflow": {
            "present": features.cashflow.present,
            "gap_detected": features.cashflow.gap_detected,
            "gap_month": features.cashflow.gap_month,
            "gap_amount": _dec(features.cashflow.gap_amount),
            "revenue_confirmed": features.cashflow.revenue_confirmed,
        },
        "mass_address": features.mass_address,
        "sources_failed": list(features.sources_failed),
        # Только если АБС ответила: снимки без оборотов в банке хешируются, как раньше.
        **({"bank_months": features.bank_months} if features.bank_months is not None else {}),
    }


def load_client_features(raw: dict[str, Any]) -> ClientFeatures:
    company, tax = raw["company"], raw["tax"]
    bureau, cashflow = raw["bureau"], raw["cashflow"]
    return ClientFeatures(
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
        cashflow=CashflowInput(
            present=cashflow["present"],
            gap_detected=cashflow["gap_detected"],
            gap_month=cashflow["gap_month"],
            gap_amount=_num(cashflow["gap_amount"]),
            revenue_confirmed=cashflow["revenue_confirmed"],
        ),
        mass_address=raw["mass_address"],
        sources_failed=tuple(raw["sources_failed"]),
        bank_months=raw.get("bank_months"),
    )


def input_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dec(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _num(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None
