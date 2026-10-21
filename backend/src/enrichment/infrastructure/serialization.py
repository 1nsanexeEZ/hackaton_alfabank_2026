"""Сериализация DTO источников в JSON и обратно — для хранения в снимке.

Деньги — строкой (точный Decimal), даты — ISO-строкой.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.enrichment.domain.snapshot import SourceData
from src.enrichment.facade import (
    CreditHistoryDTO,
    FounderDTO,
    ObligationDTO,
    RegistryExtractDTO,
    Source,
    TaxProfileDTO,
)


def data_to_json(source: Source, data: SourceData) -> dict[str, Any]:
    if isinstance(data, RegistryExtractDTO):
        return _registry_to_json(data)
    if isinstance(data, TaxProfileDTO):
        return _tax_to_json(data)
    if isinstance(data, CreditHistoryDTO):
        return _credit_to_json(data)
    raise TypeError(f"Нельзя сериализовать данные источника {source!r}")


def data_from_json(source: Source, raw: dict[str, Any]) -> SourceData:
    if source == "egrul":
        return _registry_from_json(raw)
    if source == "fns":
        return _tax_from_json(raw)
    if source == "bki":
        return _credit_from_json(raw)
    raise ValueError(f"Нельзя разобрать данные источника {source!r}")


def _dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _registry_to_json(dto: RegistryExtractDTO) -> dict[str, Any]:
    return {
        "inn": dto.inn,
        "ogrn": dto.ogrn,
        "legal_form": dto.legal_form,
        "full_name": dto.full_name,
        "status": dto.status,
        "registered_at": dto.registered_at.isoformat(),
        "okved_main": dto.okved_main,
        "okved_extra": list(dto.okved_extra),
        "head_last_name": dto.head_last_name,
        "head_first_name": dto.head_first_name,
        "head_middle_name": dto.head_middle_name,
        "head_position": dto.head_position,
        "founders": [{"name": f.name, "share_percent": str(f.share_percent)} for f in dto.founders],
        "address": dto.address,
        "region_code": dto.region_code,
        "mass_address": dto.mass_address,
    }


def _registry_from_json(raw: dict[str, Any]) -> RegistryExtractDTO:
    return RegistryExtractDTO(
        inn=raw["inn"],
        ogrn=raw["ogrn"],
        legal_form=raw["legal_form"],
        full_name=raw["full_name"],
        status=raw["status"],
        registered_at=date.fromisoformat(raw["registered_at"]),
        okved_main=raw["okved_main"],
        okved_extra=tuple(raw["okved_extra"]),
        head_last_name=raw["head_last_name"],
        head_first_name=raw["head_first_name"],
        head_middle_name=raw["head_middle_name"],
        head_position=raw["head_position"],
        founders=tuple(
            FounderDTO(name=f["name"], share_percent=Decimal(f["share_percent"]))
            for f in raw["founders"]
        ),
        address=raw["address"],
        region_code=raw["region_code"],
        mass_address=raw["mass_address"],
    )


def _tax_to_json(dto: TaxProfileDTO) -> dict[str, Any]:
    return {
        "tax_arrears": str(dto.tax_arrears),
        "avg_headcount": dto.avg_headcount,
        "reported_revenue": str(dto.reported_revenue) if dto.reported_revenue is not None else None,
        "reported_expenses": str(dto.reported_expenses)
        if dto.reported_expenses is not None
        else None,
        "report_year": dto.report_year,
        "tax_regime": dto.tax_regime,
        "disqualified_head": dto.disqualified_head,
        "in_msp_registry": dto.in_msp_registry,
    }


def _tax_from_json(raw: dict[str, Any]) -> TaxProfileDTO:
    return TaxProfileDTO(
        tax_arrears=Decimal(raw["tax_arrears"]),
        avg_headcount=raw["avg_headcount"],
        reported_revenue=_dec(raw["reported_revenue"]),
        reported_expenses=_dec(raw["reported_expenses"]),
        report_year=raw["report_year"],
        tax_regime=raw["tax_regime"],
        disqualified_head=raw["disqualified_head"],
        in_msp_registry=raw["in_msp_registry"],
    )


def _credit_to_json(dto: CreditHistoryDTO) -> dict[str, Any]:
    return {
        "obligations": [
            {
                "creditor": o.creditor,
                "kind": o.kind,
                "amount": str(o.amount),
                "balance": str(o.balance),
                "monthly_payment": str(o.monthly_payment),
                "opened_at": o.opened_at.isoformat(),
                "closes_at": o.closes_at.isoformat() if o.closes_at else None,
                "overdue_days": o.overdue_days,
            }
            for o in dto.obligations
        ],
        "inquiries_last_30d": dto.inquiries_last_30d,
        "has_active_overdue": dto.has_active_overdue,
        "max_overdue_days_12m": dto.max_overdue_days_12m,
        "total_monthly_payments": str(dto.total_monthly_payments),
    }


def _credit_from_json(raw: dict[str, Any]) -> CreditHistoryDTO:
    return CreditHistoryDTO(
        obligations=tuple(
            ObligationDTO(
                creditor=o["creditor"],
                kind=o["kind"],
                amount=Decimal(o["amount"]),
                balance=Decimal(o["balance"]),
                monthly_payment=Decimal(o["monthly_payment"]),
                opened_at=date.fromisoformat(o["opened_at"]),
                closes_at=date.fromisoformat(o["closes_at"]) if o["closes_at"] else None,
                overdue_days=o["overdue_days"],
            )
            for o in raw["obligations"]
        ),
        inquiries_last_30d=raw["inquiries_last_30d"],
        has_active_overdue=raw["has_active_overdue"],
        max_overdue_days_12m=raw["max_overdue_days_12m"],
        total_monthly_payments=Decimal(raw["total_monthly_payments"]),
    )
