"""Broken market rules. No HTTP here: infrastructure/exception_handler.py maps each error to
a response."""


class MarketError(Exception):
    default_message = "Market error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        # Machine-readable details for the response, like core AppError's.
        self.details: dict[str, object] | None = None
        super().__init__(self.message)


class InvalidKeyRateError(MarketError):
    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.details = {"field": field, "code": "invalid"}


class KeyRateDateTakenError(MarketError):
    default_message = "A key rate from this date is already entered"


class KeyRateInForceError(MarketError):
    default_message = "A key rate that has been in force is history and stays"


class KeyRateNotFoundError(MarketError):
    default_message = "Key rate not found"
