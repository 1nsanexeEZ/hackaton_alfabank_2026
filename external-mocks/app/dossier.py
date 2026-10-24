"""ГИР БО, Контур.Фокус и БКИ физлица: сценарии демо-компаний из сидов и детерминированная
генерация для остальных ИНН (тот же ИНН → тот же ответ).

Форматы — как у самих источников (`frontend/mocks/external-sources.json`): ГИР БО — коды строк
форм 0710001/0710002 в тысячах рублей, Контур — суммы в рублях, БКИ физлица — тот же отчёт, что
по компании (копейки). Годы отчётности — относительно текущего: последний закрытый год и
предыдущий.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from app.data import Company, Obligation, obligations_response

_RUB = 100  # копеек в рубле
_K = 1000 * _RUB  # тысяча рублей в копейках


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


# --- ГИР БО ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class GirBoYear:
    """Год отчётности в тысячах рублей; остальные строки форм выводятся из этих."""

    revenue: int
    cost_of_sales: int
    interest_payable: int
    equity: int
    long_term_liabilities: int = 0


# Последний закрытый год — второй.
DEMO_GIR_BO: dict[str, tuple[GirBoYear, GirBoYear]] = {
    # Ромашка: ровный рост, капитал положительный.
    "7701158817": (GirBoYear(44_000, 37_400, 420, 11_200), GirBoYear(48_000, 40_000, 380, 12_600)),
    # Вектор: строительство, долгосрочный кредит.
    "7702987976": (
        GirBoYear(27_000, 24_300, 760, 5_400, 4_000),
        GirBoYear(29_000, 26_000, 690, 5_900, 3_000),
    ),
    # Закат: выручка падает, капитал ушёл в минус.
    "7703417070": (GirBoYear(21_000, 20_500, 950, 600), GirBoYear(18_000, 21_000, 1_100, -2_400)),
    # Прогресс: та же выручка, что у ФНС (12 млн), — против заявленных 36 млн.
    "7704568152": (GirBoYear(11_000, 8_400, 310, 3_100), GirBoYear(12_000, 9_000, 290, 3_500)),
    # Сбой: обычная оптовая компания.
    "7705729405": (GirBoYear(22_000, 19_000, 400, 4_800), GirBoYear(24_000, 21_000, 380, 5_200)),
}


def _gir_bo_period(year: int, figures: GirBoYear) -> dict:
    total_assets = max(figures.revenue // 2, 1)
    fixed_assets = total_assets * 35 // 100
    inventories = total_assets * 20 // 100
    receivables = total_assets * 30 // 100
    cash = total_assets - fixed_assets - inventories - receivables
    short_term = total_assets - figures.equity - figures.long_term_liabilities
    sales_profit = figures.revenue - figures.cost_of_sales
    before_tax = sales_profit - figures.interest_payable
    net_profit = before_tax * 4 // 5 if before_tax > 0 else before_tax
    return {
        "year": year,
        "balance": {
            "1150_fixed_assets": fixed_assets,
            "1210_inventories": inventories,
            "1230_receivables": receivables,
            "1250_cash": cash,
            "1600_total_assets": total_assets,
            "1300_equity": figures.equity,
            "1400_long_term_liabilities": figures.long_term_liabilities,
            "1500_short_term_liabilities": short_term,
            # Итог пассива: капитал и обязательства.
            "1700_total_liabilities": total_assets,
        },
        "income": {
            "2110_revenue": figures.revenue,
            "2120_cost_of_sales": figures.cost_of_sales,
            "2200_sales_profit": sales_profit,
            "2330_interest_payable": figures.interest_payable,
            "2300_profit_before_tax": before_tax,
            "2400_net_profit": net_profit,
        },
    }


def _generated_gir_bo(company: Company) -> tuple[GirBoYear, GirBoYear]:
    s = _seed("gir_bo:" + company.inn)
    last = max(company.revenue_kop // _K, 1)
    previous = last * 92 // 100
    interest = last // 100 if company.bki_obligations else 0
    # Каждая двенадцатая компания — с отрицательным капиталом в последнем году.
    negative = (s >> 3) % 12 == 0
    equity = -(last // 40) if negative else last // 10
    return (
        GirBoYear(previous, previous * 82 // 100, interest, previous // 10),
        GirBoYear(last, last * 82 // 100, interest, equity),
    )


def gir_bo_response(company: Company) -> dict:
    base = {"inn": company.inn, "unit": "тыс. руб."}
    if company.form == "ИП":
        reason = "ИП не сдают бухгалтерскую отчётность в ГИР БО"
        return {**base, "available": False, "reason": reason, "periods": []}
    if company.reg_days_ago < 365:
        reason = "Компания зарегистрирована менее года назад: годовой отчётности ещё нет"
        return {**base, "available": False, "reason": reason, "periods": []}
    years = DEMO_GIR_BO.get(company.inn) or _generated_gir_bo(company)
    last_year = date.today().year - 1
    periods = [
        _gir_bo_period(last_year - 1, years[0]),
        _gir_bo_period(last_year, years[1]),
    ]
    return {**base, "available": True, "reason": None, "periods": periods}


# --- Контур.Фокус ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kontur:
    reliability: str  # green | yellow | red
    notes: tuple[str, ...] = ()
    as_defendant: int = 0
    as_plaintiff: int = 0
    defendant_sum_rub: int = 0
    enforcement_active: int = 0
    enforcement_sum_rub: int = 0
    gov_contracts: int = 0
    gov_contracts_sum_rub: int = 0
    # (дата, тип сообщения, номер дела)
    bankruptcy_messages: tuple[tuple[str, str, str], ...] = ()
    active_pledges: int = 0
    affiliated_companies: int = 0


DEMO_KONTUR: dict[str, Kontur] = {
    "7701158817": Kontur("green", as_plaintiff=1, active_pledges=1, affiliated_companies=1),
    "770669871605": Kontur(
        "yellow", ("ИП зарегистрирован менее 12 месяцев назад",), affiliated_companies=1
    ),
    "7702987976": Kontur(
        "yellow",
        ("Арбитражное дело в качестве ответчика за последний год",),
        as_defendant=1,
        as_plaintiff=2,
        defendant_sum_rub=450_000,
        gov_contracts=2,
        gov_contracts_sum_rub=6_800_000,
        active_pledges=2,
        affiliated_companies=3,
    ),
    "7703417070": Kontur(
        "red",
        (
            "Юрлицо в процессе ликвидации",
            "Приостановлены операции по счетам",
            "Налоговая задолженность",
            "Исполнительные производства",
            "Отрицательные чистые активы",
        ),
        as_defendant=6,
        defendant_sum_rub=5_200_000,
        enforcement_active=4,
        enforcement_sum_rub=2_600_000,
        active_pledges=1,
        affiliated_companies=2,
    ),
    "7704568152": Kontur("green", active_pledges=1, affiliated_companies=1),
    "7705729405": Kontur("green", as_plaintiff=3, active_pledges=1, affiliated_companies=2),
    "7706123455": Kontur("yellow", ("Компания зарегистрирована менее 12 месяцев назад",)),
    # Компании для проверки по ИНН (CHECK_DEMO в app/data.py).
    "7707177012": Kontur(
        "red",
        ("Процедура банкротства",),
        as_defendant=3,
        defendant_sum_rub=7_400_000,
        bankruptcy_messages=(
            (
                "2026-06-15",
                "Признание должника банкротом и открытие конкурсного производства",
                "А40-117701/2026",
            ),
        ),
    ),
    "7707177020": Kontur("yellow", ("Адрес массовой регистрации",), affiliated_companies=1),
    "7707177037": Kontur(
        "yellow",
        ("Налоговая задолженность", "Исполнительные производства"),
        enforcement_active=3,
        enforcement_sum_rub=1_860_000,
    ),
}


def _generated_kontur(company: Company) -> Kontur:
    s = _seed("kontur:" + company.inn)
    revenue_rub = company.revenue_kop // _RUB
    notes: list[str] = []
    bankruptcy: tuple[tuple[str, str, str], ...] = ()
    if company.status == "BANKRUPT" or (s >> 3) % 40 == 0:
        bankruptcy = (("2026-08-12", "Введение процедуры наблюдения", f"А40-{s % 90000}/2026"),)
        notes.append("Процедура банкротства")
    if company.status in ("LIQUIDATING", "LIQUIDATED"):
        notes.append("Юрлицо в процессе ликвидации")
    as_defendant, defendant_sum = 0, 0
    if (s >> 9) % 3 == 0:
        as_defendant = 1 + (s >> 11) % 3
        defendant_sum = revenue_rub * (1 + (s >> 13) % 25) // 100
        notes.append("Арбитражные дела в качестве ответчика")
    enforcement_active, enforcement_sum = 0, 0
    if company.arrears_kop:
        enforcement_active = 1 + (s >> 17) % 4
        enforcement_sum = company.arrears_kop // _RUB * (1 + (s >> 19) % 3)
        notes.append("Исполнительные производства")
    if company.account_blocks:
        notes.append("Приостановлены операции по счетам")
    if bankruptcy or company.status != "ACTIVE":
        reliability = "red"
    elif notes:
        reliability = "yellow"
    else:
        reliability = "green"
    return Kontur(
        reliability,
        tuple(notes),
        as_defendant=as_defendant,
        as_plaintiff=(s >> 21) % 4,
        defendant_sum_rub=defendant_sum,
        enforcement_active=enforcement_active,
        enforcement_sum_rub=enforcement_sum,
        gov_contracts=(s >> 23) % 3,
        gov_contracts_sum_rub=(s >> 23) % 3 * 1_500_000,
        bankruptcy_messages=bankruptcy,
        active_pledges=len(company.bki_obligations),
        affiliated_companies=(s >> 25) % 5,
    )


def kontur_response(company: Company) -> dict:
    kontur = DEMO_KONTUR.get(company.inn) or _generated_kontur(company)
    return {
        "inn": company.inn,
        "reliability": kontur.reliability,
        "reliability_notes": list(kontur.notes),
        "arbitration": {
            "as_defendant": kontur.as_defendant,
            "as_plaintiff": kontur.as_plaintiff,
            "defendant_sum_rub": kontur.defendant_sum_rub,
        },
        "enforcement_proceedings": {
            "active": kontur.enforcement_active,
            "sum_rub": kontur.enforcement_sum_rub,
        },
        "gov_contracts": {"count": kontur.gov_contracts, "sum_rub": kontur.gov_contracts_sum_rub},
        "bankruptcy_messages": [
            {"date": when, "type": kind, "case": case}
            for when, kind, case in kontur.bankruptcy_messages
        ],
        "active_pledges": kontur.active_pledges,
        "affiliated_companies": kontur.affiliated_companies,
        "checked_at": date.today().isoformat(),
    }


# --- БКИ физлица ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonHistory:
    obligations: tuple[Obligation, ...]
    inquiries_30d: int


# Руководители демо-компаний по ИНН компании; ответ — только если ФИО совпало с реестром.
DEMO_HEADS: dict[str, PersonHistory] = {
    "7701158817": PersonHistory(
        (
            Obligation(
                "mortgage",
                "АО «Банк»",
                6_000 * _K,
                4_200 * _K,
                52 * _K,
                "2021-04-15",
                "2041-04-15",
                0,
                0,
            ),
            Obligation(
                "card", "АО «Банк»", 300 * _K, 40 * _K, 6 * _K, "2022-09-01", "2027-09-01", 0, 0
            ),
        ),
        0,
    ),
    "770669871605": PersonHistory((), 0),
    "7702987976": PersonHistory(
        (
            Obligation(
                "consumer",
                "ПАО «Кредит»",
                1_500 * _K,
                600 * _K,
                38 * _K,
                "2023-02-10",
                "2027-02-10",
                0,
                12,
            ),
        ),
        1,
    ),
    # Закатов: текущая просрочка 45 дней по потребительскому кредиту.
    "7703417070": PersonHistory(
        (
            Obligation(
                "consumer",
                "ПАО «Кредит»",
                800 * _K,
                650 * _K,
                27 * _K,
                "2024-03-01",
                "2028-03-01",
                45,
                45,
            ),
            Obligation(
                "card", "АО «Банк»", 200 * _K, 195 * _K, 10 * _K, "2023-06-01", "2028-06-01", 0, 0
            ),
        ),
        4,
    ),
    "7704568152": PersonHistory(
        (
            Obligation(
                "card", "АО «Банк»", 150 * _K, 20 * _K, 3 * _K, "2024-01-20", "2029-01-20", 0, 0
            ),
        ),
        1,
    ),
    "7705729405": PersonHistory((), 0),
    # Стартов, учредитель стартапа: кредитная карта без просрочек — предскрин проходит.
    "7706123455": PersonHistory(
        (
            Obligation(
                "card", "АО «Банк»", 250 * _K, 30 * _K, 5 * _K, "2023-11-01", "2028-11-01", 0, 0
            ),
        ),
        1,
    ),
}


def normalized_name(*parts: str | None) -> str:
    """Для сверки ФИО: нижний регистр, ё → е, одиночные пробелы."""
    text = " ".join(p for p in parts if p)
    return " ".join(text.lower().replace("ё", "е").split())


def _generated_person(name: str, company_inn: str | None) -> PersonHistory:
    s = _seed(f"person:{name}:{company_inn or ''}")
    if s % 4 == 0:
        return PersonHistory((), 0)
    overdue = 0 if (s >> 3) % 6 else 5 + (s >> 5) % 90
    loan = Obligation(
        "consumer",
        "АО «Банк»",
        (300 + (s >> 9) % 1700) * _K,
        (100 + (s >> 13) % 900) * _K,
        (10 + (s >> 17) % 60) * _K,
        "2024-01-01",
        "2029-01-01",
        overdue,
        max(overdue, (s >> 21) % 20),
    )
    return PersonHistory((loan,), (s >> 25) % 5)


def person_history(
    company: Company | None, last_name: str, first_name: str, middle_name: str | None
) -> PersonHistory:
    name = normalized_name(last_name, first_name, middle_name)
    if company is not None and company.inn in DEMO_HEADS:
        if normalized_name(company.head_fio) == name:
            return DEMO_HEADS[company.inn]
    return _generated_person(name, company.inn if company is not None else None)


def person_report_response(
    history: PersonHistory, last_name: str, first_name: str, middle_name: str | None
) -> dict:
    return {
        "subject": {"last_name": last_name, "first_name": first_name, "middle_name": middle_name},
        "obligations": obligations_response(history.obligations),
        "inquiries_30d": history.inquiries_30d,
    }
