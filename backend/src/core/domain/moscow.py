"""Moscow time: the bank's calendar day (key rate dates, contract dates)."""

from datetime import UTC, date, datetime, timedelta, timezone

from src.core.domain.clock import Clock

MSK = timezone(timedelta(hours=3), "МСК")


def in_moscow(moment: datetime) -> datetime:
    """A naive moment is taken as UTC, as the database returns it on SQLite."""
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    return aware.astimezone(MSK)


def moscow_today(clock: Clock) -> date:
    return in_moscow(clock.now()).date()
