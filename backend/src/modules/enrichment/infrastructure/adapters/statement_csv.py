"""Выписка клиента в CSV (UTF-8, разделитель `;`) → операции для прогноза."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from src.modules.enrichment.application.interfaces.statement_parser import StatementParser
from src.modules.enrichment.domain.cashflow import Transaction
from src.modules.enrichment.domain.exceptions import StatementParseError

_REQUIRED_COLUMNS = ("date", "amount")


class CsvStatementParser(StatementParser):
    def parse(self, content: bytes) -> list[Transaction]:
        """CSV (UTF-8, разделитель `;`) → список операций. Пустой файл → []."""
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise StatementParseError("Файл не в кодировке UTF-8") from None
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        if reader.fieldnames is None:
            return []
        fields = [f.strip().lower() for f in reader.fieldnames]
        missing = [c for c in _REQUIRED_COLUMNS if c not in fields]
        if missing:
            if len(fields) == 1 and "," in fields[0]:
                raise StatementParseError(
                    "Разделитель колонок — точка с запятой «;», а не запятая", line=1
                )
            raise StatementParseError(f"В выписке нет колонок: {', '.join(missing)}", line=1)
        reader.fieldnames = fields
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
                raise StatementParseError(
                    f"Строка {line_no}: дата «{raw_date}» должна быть ГГГГ-ММ-ДД, сумма "
                    f"«{raw_amount}» — числом через точку, без пробелов и валюты",
                    line=line_no,
                ) from exc
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
