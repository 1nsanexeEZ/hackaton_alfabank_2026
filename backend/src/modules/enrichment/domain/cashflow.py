"""Прогноз кассового разрыва по выпискам — объяснимый, без ML.

Выписка клиента — внутренние данные (источник `statement`), не внешний мок. Парсер и расчёт —
чистый Python (stdlib), чтобы домен ни от чего не зависел. Результат кладётся в снимок как
`CashflowForecastDTO`; суммы считаются в Decimal и округляются до копеек.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from src.modules.enrichment.facade import (
    CashflowForecastDTO,
    CashflowMonthDTO,
    CashflowProjectionDTO,
)

_CENT = Decimal("0.01")
_REQUIRED_COLUMNS = ("date", "amount")
_FORECAST_HORIZON = 3
_REVENUE_CONFIRM_RATIO = Decimal("0.7")  # оборот ≥ 70% заявленной выручки — подтверждает


class StatementParseError(Exception):
    """Выписка в неверном формате — показываем понятную ошибку, не роняем обогащение."""


@dataclass(frozen=True, slots=True)
class Transaction:
    txn_date: date
    amount: Decimal  # > 0 — поступление, < 0 — списание
    counterparty_inn: str | None = None
    counterparty_name: str | None = None
    purpose: str | None = None


def parse_statement(data: bytes) -> list[Transaction]:
    """CSV (UTF-8, разделитель `;`) → список операций. Пустой файл → []."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";")
    if reader.fieldnames is None:
        return []
    missing = [c for c in _REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise StatementParseError(f"В выписке нет колонок: {', '.join(missing)}")
    transactions: list[Transaction] = []
    for line_no, row in enumerate(reader, start=2):
        raw_date = (row.get("date") or "").strip()
        raw_amount = (row.get("amount") or "").strip()
        if not raw_date and not raw_amount:
            continue
        try:
            txn_date = date.fromisoformat(raw_date)
            amount = Decimal(raw_amount)
        except (ValueError, InvalidOperation) as exc:
            raise StatementParseError(f"Строка {line_no}: некорректные дата или сумма") from exc
        transactions.append(
            Transaction(
                txn_date=txn_date,
                amount=amount,
                counterparty_inn=(row.get("counterparty_inn") or "").strip() or None,
                counterparty_name=(row.get("counterparty_name") or "").strip() or None,
                purpose=(row.get("purpose") or "").strip() or None,
            )
        )
    return transactions


def build_forecast(
    transactions: list[Transaction],
    *,
    current_monthly_payments: Decimal,
    new_loan_payment: Decimal,
    declared_annual_revenue: Decimal | None,
    as_of: date,
    statement_document_ids: tuple[UUID, ...],
) -> CashflowForecastDTO:
    history = _monthly_history(transactions)
    nets = [m.net for m in history]
    avg_net = sum(nets, Decimal(0)) / len(nets) if nets else Decimal(0)
    seasonality = _seasonality(history, avg_net)

    # Прогноз — чистый денежный поток с новым кредитом нарастающим итогом от нуля:
    # уход в минус = бизнесу не хватает операционного потока покрыть платёж.
    forecast: list[CashflowProjectionDTO] = []
    balance = Decimal(0)
    year, month = _last_month(history, as_of)
    for _ in range(_FORECAST_HORIZON):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        projected_net = (
            avg_net * seasonality.get(month, Decimal(1))
            - current_monthly_payments
            - new_loan_payment
        )
        balance = (balance + projected_net).quantize(_CENT)
        forecast.append(
            CashflowProjectionDTO(month=f"{year:04d}-{month:02d}", projected_balance=balance)
        )

    negatives = [p for p in forecast if p.projected_balance < 0]
    annual_inflow = sum((m.inflow for m in history), Decimal(0))
    return CashflowForecastDTO(
        months_history=tuple(history),
        forecast=tuple(forecast),
        gap_detected=bool(negatives),
        gap_month=negatives[0].month if negatives else None,
        gap_amount=(-min(p.projected_balance for p in forecast)).quantize(_CENT)
        if negatives
        else None,
        annual_inflow=annual_inflow.quantize(_CENT),
        revenue_confirmed=_revenue_confirmed(annual_inflow, declared_annual_revenue),
        method="средний чистый поток × сезонность − платежи по кредитам − платёж по новому кредиту",
        statement_document_ids=statement_document_ids,
    )


def _monthly_history(transactions: list[Transaction]) -> list[CashflowMonthDTO]:
    buckets: dict[str, list[Decimal]] = {}
    for txn in transactions:
        key = f"{txn.txn_date.year:04d}-{txn.txn_date.month:02d}"
        agg = buckets.setdefault(key, [Decimal(0), Decimal(0)])
        if txn.amount >= 0:
            agg[0] += txn.amount
        else:
            agg[1] += -txn.amount
    history: list[CashflowMonthDTO] = []
    balance = Decimal(0)
    for key in sorted(buckets):
        inflow, outflow = buckets[key]
        net = inflow - outflow
        balance += net
        history.append(
            CashflowMonthDTO(
                month=key,
                inflow=inflow.quantize(_CENT),
                outflow=outflow.quantize(_CENT),
                net=net.quantize(_CENT),
                balance=balance.quantize(_CENT),
            )
        )
    return history


def _seasonality(history: list[CashflowMonthDTO], avg_net: Decimal) -> dict[int, Decimal]:
    # Индекс «поток месяца / средний поток» осмыслен только при положительном среднем: при
    # отрицательном знак переворачивается, и прогноз повторяет удачные месяцы прошлого года,
    # не видя падения. Бизнес в среднем сжигает деньги — прогнозируем средним потоком.
    if avg_net <= 0:
        return {}
    by_month: dict[int, list[Decimal]] = {}
    for item in history:
        by_month.setdefault(int(item.month[5:7]), []).append(item.net)
    return {
        month: (sum(values, Decimal(0)) / len(values)) / avg_net
        for month, values in by_month.items()
    }


def _last_month(history: list[CashflowMonthDTO], as_of: date) -> tuple[int, int]:
    if history:
        last = history[-1].month
        return int(last[:4]), int(last[5:7])
    return as_of.year, as_of.month


def _revenue_confirmed(annual_inflow: Decimal, declared: Decimal | None) -> bool | None:
    if declared is None or declared <= 0:
        return None
    return bool(annual_inflow / declared >= _REVENUE_CONFIRM_RATIO)
