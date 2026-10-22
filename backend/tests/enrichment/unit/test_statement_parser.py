from __future__ import annotations

from decimal import Decimal

import pytest

from src.enrichment.domain.cashflow import StatementParseError, parse_statement

_HEADER = "date;amount;counterparty_inn;counterparty_name;purpose\n"


def test_parses_inflow_and_outflow() -> None:
    data = (
        _HEADER
        + "2026-01-05;150000.00;7701234567;ООО Поставщик;Оплата по счёту\n"
        + "2026-01-06;-48000.00;;Аренда;Аренда за январь\n"
    ).encode()
    txns = parse_statement(data)
    assert len(txns) == 2
    assert txns[0].amount == Decimal("150000.00")
    assert txns[0].counterparty_inn == "7701234567"
    assert txns[1].amount == Decimal("-48000.00")


def test_empty_file_and_header_only_give_no_transactions() -> None:
    assert parse_statement(b"") == []
    assert parse_statement(_HEADER.encode()) == []


def test_missing_required_columns_raises() -> None:
    with pytest.raises(StatementParseError):
        parse_statement(b"foo;bar\n1;2\n")


def test_malformed_row_raises() -> None:
    with pytest.raises(StatementParseError):
        parse_statement((_HEADER + "notadate;abc;;;\n").encode())


def test_blank_rows_are_skipped() -> None:
    data = (_HEADER + "2026-01-05;100.00;;;\n;;;;\n").encode()
    assert len(parse_statement(data)) == 1
