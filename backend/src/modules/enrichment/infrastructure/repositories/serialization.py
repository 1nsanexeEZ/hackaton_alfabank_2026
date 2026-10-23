"""Сериализация DTO источников в JSON и обратно — для хранения в снимке.

Деньги — строкой (точный Decimal), даты — ISO-строкой.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date
from decimal import Decimal
from typing import Any
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
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, ObligationDTO
from src.modules.enrichment.application.dto.registry import FounderDTO, RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import SourceData
from src.modules.enrichment.application.dto.tax import AccountBlockDTO, TaxProfileDTO
from src.modules.enrichment.domain.enums import Source

# Поля периода ГИР БО: все суммы, кроме года.
_PERIOD_AMOUNTS = tuple(f.name for f in fields(AccountingPeriodDTO) if f.name != "year")


def data_to_json(source: Source, data: object) -> dict[str, Any]:
    if isinstance(data, RegistryExtractDTO):
        return _registry_to_json(data)
    if isinstance(data, TaxProfileDTO):
        return _tax_to_json(data)
    if isinstance(data, CreditHistoryDTO):
        return _credit_to_json(data)
    if isinstance(data, CashflowForecastDTO):
        return _cashflow_to_json(data)
    if isinstance(data, AccountingReportsDTO):
        return _accounting_to_json(data)
    if isinstance(data, CounterpartyRiskDTO):
        return _counterparty_to_json(data)
    if isinstance(data, AmlCheckDTO):
        return _aml_to_json(data)
    if isinstance(data, BankStopListDTO):
        return {
            "listed": data.listed,
            "reason": data.reason,
            "listed_at": data.listed_at.isoformat() if data.listed_at else None,
        }
    if isinstance(data, BankTurnoverDTO):
        return {
            "client_since": data.client_since.isoformat() if data.client_since else None,
            "months": [
                {"month": m.month, "inflow": str(m.inflow), "outflow": str(m.outflow)}
                for m in data.months
            ],
        }
    raise TypeError(f"Нельзя сериализовать данные источника {source!r}")


def data_from_json(source: Source, raw: dict[str, Any]) -> SourceData:
    if source == "egrul":
        return _registry_from_json(raw)
    if source == "fns":
        return _tax_from_json(raw)
    if source in ("bki", "bki_head"):
        return _credit_from_json(raw)
    if source == "statement":
        return _cashflow_from_json(raw)
    if source == "gir_bo":
        return _accounting_from_json(raw)
    if source == "kontur":
        return _counterparty_from_json(raw)
    if source == "aml":
        return _aml_from_json(raw)
    if source == "bank_stop_list":
        return BankStopListDTO(
            listed=raw["listed"],
            reason=raw["reason"],
            listed_at=date.fromisoformat(raw["listed_at"]) if raw["listed_at"] else None,
        )
    if source == "bank_turnover":
        return BankTurnoverDTO(
            client_since=date.fromisoformat(raw["client_since"]) if raw["client_since"] else None,
            months=tuple(
                TurnoverMonthDTO(
                    month=m["month"], inflow=Decimal(m["inflow"]), outflow=Decimal(m["outflow"])
                )
                for m in raw["months"]
            ),
        )
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
        "founders": [
            {"name": f.name, "share_percent": str(f.share_percent), "inn": f.inn}
            for f in dto.founders
        ],
        "address": dto.address,
        "region_code": dto.region_code,
        "mass_address": dto.mass_address,
        "kpp": dto.kpp,
        "head_since": dto.head_since.isoformat() if dto.head_since else None,
        "unreliable": list(dto.unreliable),
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
            FounderDTO(name=f["name"], share_percent=Decimal(f["share_percent"]), inn=f.get("inn"))
            for f in raw["founders"]
        ),
        address=raw["address"],
        region_code=raw["region_code"],
        mass_address=raw["mass_address"],
        kpp=raw.get("kpp"),
        head_since=date.fromisoformat(raw["head_since"]) if raw.get("head_since") else None,
        # Снимки до отметок о недостоверности хранились без них.
        unreliable=tuple(raw.get("unreliable", ())),
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
        "mass_head": dto.mass_head,
        "account_blocks": [
            {
                "decision_number": b.decision_number,
                "date": b.date.isoformat(),
                "authority_code": b.authority_code,
                "reason": b.reason,
            }
            for b in dto.account_blocks
        ],
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
        # Снимки до ГИР БО и Контура хранились без блокировок.
        account_blocks=tuple(
            AccountBlockDTO(
                decision_number=b["decision_number"],
                date=date.fromisoformat(b["date"]),
                authority_code=b["authority_code"],
                reason=b["reason"],
            )
            for b in raw.get("account_blocks", [])
        ),
        mass_head=raw.get("mass_head"),
    )


def _accounting_to_json(dto: AccountingReportsDTO) -> dict[str, Any]:
    return {
        "available": dto.available,
        "reason": dto.reason,
        "periods": [
            {"year": p.year, **{name: str(getattr(p, name)) for name in _PERIOD_AMOUNTS}}
            for p in dto.periods
        ],
    }


def _accounting_from_json(raw: dict[str, Any]) -> AccountingReportsDTO:
    return AccountingReportsDTO(
        available=raw["available"],
        reason=raw["reason"],
        periods=tuple(
            AccountingPeriodDTO(
                year=p["year"], **{name: Decimal(p[name]) for name in _PERIOD_AMOUNTS}
            )
            for p in raw["periods"]
        ),
    )


def _counterparty_to_json(dto: CounterpartyRiskDTO) -> dict[str, Any]:
    return {
        "reliability": dto.reliability,
        "notes": list(dto.notes),
        "arbitration": {
            "as_defendant": dto.arbitration.as_defendant,
            "as_plaintiff": dto.arbitration.as_plaintiff,
            "defendant_sum": str(dto.arbitration.defendant_sum),
        },
        "enforcement": {"active": dto.enforcement.active, "sum": str(dto.enforcement.sum)},
        "bankruptcy_messages": [
            {"date": m.date.isoformat(), "type": m.type, "case": m.case}
            for m in dto.bankruptcy_messages
        ],
        "gov_contracts": {"count": dto.gov_contracts.count, "sum": str(dto.gov_contracts.sum)},
        "active_pledges": dto.active_pledges,
    }


def _counterparty_from_json(raw: dict[str, Any]) -> CounterpartyRiskDTO:
    arbitration, enforcement, contracts = (
        raw["arbitration"],
        raw["enforcement"],
        raw["gov_contracts"],
    )
    return CounterpartyRiskDTO(
        reliability=raw["reliability"],
        notes=tuple(raw["notes"]),
        arbitration=ArbitrationDTO(
            as_defendant=arbitration["as_defendant"],
            as_plaintiff=arbitration["as_plaintiff"],
            defendant_sum=Decimal(arbitration["defendant_sum"]),
        ),
        enforcement=EnforcementDTO(active=enforcement["active"], sum=Decimal(enforcement["sum"])),
        bankruptcy_messages=tuple(
            BankruptcyMessageDTO(date=date.fromisoformat(m["date"]), type=m["type"], case=m["case"])
            for m in raw["bankruptcy_messages"]
        ),
        gov_contracts=GovContractsDTO(count=contracts["count"], sum=Decimal(contracts["sum"])),
        active_pledges=raw["active_pledges"],
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


def _cashflow_to_json(dto: CashflowForecastDTO) -> dict[str, Any]:
    return {
        "months_history": [
            {
                "month": m.month,
                "inflow": str(m.inflow),
                "outflow": str(m.outflow),
                "net": str(m.net),
                "balance": str(m.balance),
            }
            for m in dto.months_history
        ],
        "forecast": [
            {"month": p.month, "projected_balance": str(p.projected_balance)} for p in dto.forecast
        ],
        "gap_detected": dto.gap_detected,
        "gap_month": dto.gap_month,
        "gap_amount": str(dto.gap_amount) if dto.gap_amount is not None else None,
        "annual_inflow": str(dto.annual_inflow),
        "revenue_confirmed": dto.revenue_confirmed,
        "method": dto.method,
        "statement_document_ids": [str(x) for x in dto.statement_document_ids],
    }


def _cashflow_from_json(raw: dict[str, Any]) -> CashflowForecastDTO:
    return CashflowForecastDTO(
        months_history=tuple(
            CashflowMonthDTO(
                month=m["month"],
                inflow=Decimal(m["inflow"]),
                outflow=Decimal(m["outflow"]),
                net=Decimal(m["net"]),
                balance=Decimal(m["balance"]),
            )
            for m in raw["months_history"]
        ),
        forecast=tuple(
            CashflowProjectionDTO(
                month=p["month"], projected_balance=Decimal(p["projected_balance"])
            )
            for p in raw["forecast"]
        ),
        gap_detected=raw["gap_detected"],
        gap_month=raw["gap_month"],
        gap_amount=_dec(raw["gap_amount"]),
        annual_inflow=Decimal(raw["annual_inflow"]),
        revenue_confirmed=raw["revenue_confirmed"],
        method=raw["method"],
        statement_document_ids=tuple(UUID(x) for x in raw["statement_document_ids"]),
    )


def _subject_to_json(dto: AmlSubjectDTO) -> dict[str, Any]:
    return {"role": dto.role, "name": dto.name, "inn": dto.inn}


def _subject_from_json(raw: dict[str, Any]) -> AmlSubjectDTO:
    return AmlSubjectDTO(role=raw["role"], name=raw["name"], inn=raw.get("inn"))


def _aml_to_json(dto: AmlCheckDTO) -> dict[str, Any]:
    return {
        "lists_date": dto.lists_date.isoformat(),
        "zsk": {"level": dto.zsk.level, "as_of": dto.zsk.as_of.isoformat()},
        "beneficial_owners": [
            {
                "name": owner.name,
                "basis": owner.basis,
                "share_percent": str(owner.share_percent)
                if owner.share_percent is not None
                else None,
            }
            for owner in dto.beneficial_owners
        ],
        "subjects": [_subject_to_json(subject) for subject in dto.subjects],
        "list_hits": [
            {"subject": _subject_to_json(hit.subject), "list": hit.list, "record": hit.record}
            for hit in dto.list_hits
        ],
        "pep_hits": [
            {"subject": _subject_to_json(hit.subject), "kind": hit.kind, "position": hit.position}
            for hit in dto.pep_hits
        ],
    }


def _aml_from_json(raw: dict[str, Any]) -> AmlCheckDTO:
    return AmlCheckDTO(
        lists_date=date.fromisoformat(raw["lists_date"]),
        zsk=ZskRiskDTO(level=raw["zsk"]["level"], as_of=date.fromisoformat(raw["zsk"]["as_of"])),
        beneficial_owners=tuple(
            BeneficialOwnerDTO(
                name=owner["name"],
                basis=owner["basis"],
                share_percent=_dec(owner["share_percent"]),
            )
            for owner in raw["beneficial_owners"]
        ),
        subjects=tuple(_subject_from_json(subject) for subject in raw["subjects"]),
        list_hits=tuple(
            ListHitDTO(
                subject=_subject_from_json(hit["subject"]), list=hit["list"], record=hit["record"]
            )
            for hit in raw["list_hits"]
        ),
        pep_hits=tuple(
            PepHitDTO(
                subject=_subject_from_json(hit["subject"]),
                kind=hit["kind"],
                position=hit["position"],
            )
            for hit in raw["pep_hits"]
        ),
    )
