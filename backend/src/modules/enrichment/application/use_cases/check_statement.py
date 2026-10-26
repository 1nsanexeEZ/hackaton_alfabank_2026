"""Use case CheckStatement: разберётся ли файл выписки — до того, как заявку подадут."""

from __future__ import annotations

from src.modules.enrichment.application.dto.cashflow import StatementCheckDTO
from src.modules.enrichment.application.interfaces.statement_parser import StatementParser
from src.modules.enrichment.domain.exceptions import StatementParseError


class CheckStatementUseCase:
    """Тот же разбор, что у прогноза кассового разрыва: правила формата живут в одном месте."""

    def __init__(self, parser: StatementParser) -> None:
        self._parser = parser

    def execute(self, content: bytes) -> StatementCheckDTO:
        try:
            operations = self._parser.parse(content)
        except StatementParseError as error:
            return StatementCheckDTO(False, 0, error.line, error.message)
        if not operations:
            return StatementCheckDTO(False, 0, None, "В выписке нет операций")
        return StatementCheckDTO(True, len(operations))
