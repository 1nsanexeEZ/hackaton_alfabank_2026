from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Test clock: returns the same moment until moved explicitly."""

    def __init__(self, moment: datetime | None = None) -> None:
        self._moment = moment or datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        if self._moment.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware datetime")

    def now(self) -> datetime:
        return self._moment

    def advance(self, delta: timedelta) -> None:
        self._moment += delta

    def set(self, moment: datetime) -> None:
        self._moment = moment
