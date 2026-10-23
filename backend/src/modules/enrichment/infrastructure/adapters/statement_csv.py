"""Выписка клиента в CSV (UTF-8, разделитель `;`) → операции для прогноза."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from src.modules.enrichment.domain.cashflow import Transaction
from src.modules.enrichment.domain.exceptions import StatementParseError

_REQUIRED_COLUMNS = ("date", "amount")


class CsvStatementParser:
    def parse(self, content: bytes) -> list[Transaction]:
        """CSV (UTF-8, разделитель `;`) → список операций. Пустой файл → []."""
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
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
