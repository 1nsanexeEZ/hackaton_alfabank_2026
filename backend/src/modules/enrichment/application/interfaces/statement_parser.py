"""Разбор файла банковской выписки в операции."""

from __future__ import annotations

from typing import Protocol

from src.modules.enrichment.domain.cashflow import Transaction


class StatementParser(Protocol):
    def parse(self, content: bytes) -> list[Transaction]:
        """Пустой файл → []; неверный формат → `StatementParseError`."""
        ...
