"""Ошибки модуля: источник не ответил или не знает субъекта, выписка не разобралась."""

from __future__ import annotations


class SourceFetchError(Exception):
    """Ошибка обращения к источнику. `kind` — timeout | unavailable | not_found | bad_response."""

    def __init__(self, kind: str, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.kind = kind
        self.attempts = attempts


class SourceNotFound(SourceFetchError):
    def __init__(self, message: str = "not found", *, attempts: int = 1) -> None:
        super().__init__("not_found", message, attempts=attempts)


class SourceUnavailable(SourceFetchError):
    pass


class StatementParseError(Exception):
    """Выписка в неверном формате — показываем понятную ошибку, не роняем обогащение."""
