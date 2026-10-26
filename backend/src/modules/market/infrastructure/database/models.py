"""SQLAlchemy models of market. Tables are prefixed with `market_`."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base


class KeyRateRecord(Base):
    """One row per date the rate changes; the rate on a day is the latest row not after it."""

    __tablename__ = "market_key_rates"
    __table_args__ = (CheckConstraint("value >= 0 AND value <= 100", name="value_range"),)

    effective_from: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    decided_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    # The admin's account; no foreign key: identity owns its table.
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
