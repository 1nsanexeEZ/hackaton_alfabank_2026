"""SQLAlchemy-модели scoring. Таблицы с префиксом `scoring_`."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType


class ScoringResultRecord(Base):
    __tablename__ = "scoring_results"
    __table_args__ = (Index("ix_scoring_results_application", "application_id", "computed_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    application_id: Mapped[UUID] = mapped_column(Uuid)
    requested_by_command: Mapped[UUID] = mapped_column(Uuid, unique=True)
    model_version: Mapped[str] = mapped_column(String(32))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType)
    input_hash: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(1))
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    flags: Mapped[list[str]] = mapped_column(JSONType)
    bank_notes: Mapped[list[str]] = mapped_column(JSONType)
    data_completeness: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # PD-модель (scoring_0002); у результатов scorecard_v1 — пусто.
    segment: Mapped[str | None] = mapped_column(String(16), default=None)
    scorecard: Mapped[str | None] = mapped_column(String(32), default=None)
    pd_12m: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), default=None)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSONType, default=None)
    # ML-модель (scoring_0003): версия, PD, скор, грейд, факторы и коды причин; до неё — пусто.
    ml: Mapped[dict[str, Any] | None] = mapped_column(JSONType, default=None)
