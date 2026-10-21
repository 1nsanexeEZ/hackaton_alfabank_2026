"""Фиксированные входы scoring для golden-тестов — на демо-данных §9.

Параметры компании берём из `seed.demo_data` (ИНН/возраст/выручка/ОКВЭД), а параметры запроса,
бюро и прогноза по выписке задаём под сценарий. Поменялась карта — видно по diff golden-файлов,
какие сценарии сдвинулись.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from seed.demo_data import COMPANIES_BY_CODE, FINANCIALS_BY_CODE
from src.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)

_AS_OF = date(2026, 10, 21)
_NO_CASHFLOW = CashflowInput(False, None, None, None, None)


def _company(code: str, *, verification: str = "verified") -> CompanyInput:
    company = COMPANIES_BY_CODE[code]
    finance = FINANCIALS_BY_CODE[code]
    return CompanyInput(
        legal_form=company.legal_form,
        business_age_months=company.registered_months_ago,
        okved_main=company.okved_main,
        verification_status=verification,
        registry_status=company.registry_status,
        declared_revenue=finance.declared_revenue,
        declared_revenue_previous=finance.declared_revenue_previous_year,
        monthly_debt_payments_declared=None,
    )


def _tax(code: str) -> TaxInput:
    finance = FINANCIALS_BY_CODE[code]
    return TaxInput(tax_arrears=finance.tax_arrears, reported_revenue=finance.fns_revenue)


def _request(
    amount: str,
    term: int,
    *,
    product: str = "UNSECURED",
    facility: str = "term_loan",
    rate: str = "21.5",
) -> RequestInput:
    return RequestInput(Decimal(amount), term, product, facility, Decimal(rate))


def _scenario(
    *,
    code: str,
    request: RequestInput,
    bureau: BureauInput,
    verification: str = "verified",
    collateral: Decimal | None = None,
    cashflow: CashflowInput = _NO_CASHFLOW,
    sources_failed: tuple[str, ...] = (),
) -> ScoringInput:
    return ScoringInput(
        request=request,
        company=_company(code, verification=verification),
        tax=_tax(code),
        bureau=bureau,
        collateral=CollateralInput(collateral),
        cashflow=cashflow,
        mass_address=False,
        sources_failed=sources_failed,
        as_of=_AS_OF,
    )


# romashka — чистый клиент, заявка в пределах выручки, без выписки.
_ROMASHKA_S1 = _scenario(
    code="romashka",
    request=_request("3000000", 24),
    bureau=BureauInput(True, True, 0, 0, Decimal("180000")),
)

# ivanov — молодой ИП, тонкое досье, с выпиской и прогнозируемым разрывом.
_IVANOV_S2 = _scenario(
    code="ivanov",
    request=_request("5000000", 24),
    bureau=BureauInput(True, False, None, 0, Decimal(0)),
    cashflow=CashflowInput(True, True, "2026-11", Decimal("300000.00"), True),
)

# vector — расхождение с реестром (директор), кредитная линия.
_VECTOR_S3 = _scenario(
    code="vector",
    request=_request(
        "10000000", 24, product="CREDIT_LINE", facility="credit_line_revolving", rate="23.0"
    ),
    bureau=BureauInput(True, True, 0, 1, Decimal("400000")),
    verification="mismatch",
)

# zakat — ликвидация, просрочка 120 дней, налоговая недоимка.
_ZAKAT_S4 = _scenario(
    code="zakat",
    request=_request("2000000", 12),
    bureau=BureauInput(True, True, 120, 2, Decimal("300000")),
)

# progress — заявленная выручка втрое выше ФНС (расхождение).
_PROGRESS_S5 = _scenario(
    code="progress",
    request=_request(
        "8000000", 24, product="CREDIT_LINE", facility="credit_line_revolving", rate="23.0"
    ),
    bureau=BureauInput(True, True, 0, 1, Decimal("250000")),
)

# sboy — БКИ недоступно (мок 503): не штрафуем за свой сбой, но ставим флаг.
_SBOY_S6 = _scenario(
    code="sboy",
    request=_request("1000000", 12),
    bureau=BureauInput(False, False, None, None, Decimal(0)),
    sources_failed=("bki",),
)

# romashka — ипотека с залогом (фактор collateral_coverage).
_ROMASHKA_MORTGAGE_S7 = _scenario(
    code="romashka",
    request=_request("30000000", 120, product="MORTGAGE", rate="18.0"),
    bureau=BureauInput(True, True, 0, 0, Decimal("180000")),
    collateral=Decimal("50000000"),
)

SCENARIOS: dict[str, ScoringInput] = {
    "romashka_s1": _ROMASHKA_S1,
    "ivanov_s2": _IVANOV_S2,
    "vector_s3": _VECTOR_S3,
    "zakat_s4": _ZAKAT_S4,
    "progress_s5": _PROGRESS_S5,
    "sboy_s6": _SBOY_S6,
    "romashka_mortgage_s7": _ROMASHKA_MORTGAGE_S7,
}
