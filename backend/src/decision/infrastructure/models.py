"""SQLAlchemy-модели decision. Таблицы с префиксом `decision_`."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType

MONEY = Numeric(18, 2)
RATE = Numeric(5, 2)


class DecisionResultRecord(Base):
    """Решение по заявке. Неизменяемое: ручное решение — новая строка с `override_of`.

    `sequence` — порядковый номер решения внутри заявки: последнее решение — с наибольшим
    номером, даже если часы не сдвинулись (замороженные часы в тестах, одна секунда в проде)."""

    __tablename__ = "decision_results"
    __table_args__ = (UniqueConstraint("application_id", "sequence"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    application_id: Mapped[UUID] = mapped_column(Uuid)
    sequence: Mapped[int] = mapped_column(Integer)
    requested_by_command: Mapped[UUID] = mapped_column(Uuid, unique=True)
    policy_version: Mapped[str] = mapped_column(String(32))
    key_rate: Mapped[Decimal] = mapped_column(RATE)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONType)
    outcome: Mapped[str] = mapped_column(String(16))
    terms: Mapped[dict[str, Any] | None] = mapped_column(JSONType, default=None)
    alternative_product_code: Mapped[str | None] = mapped_column(String(32), default=None)
    reason_codes: Mapped[list[str]] = mapped_column(JSONType)
    client_explanation: Mapped[str] = mapped_column(Text)
    improvement_hints: Mapped[list[str]] = mapped_column(JSONType)
    requested_info: Mapped[dict[str, Any] | None] = mapped_column(JSONType, default=None)
    rule_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONType)
    decided_by_type: Mapped[str] = mapped_column(String(16))
    decided_by_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    override_of: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PreApprovedOfferRecord(Base):
    """Предодобрение: одно на компанию и продукт, пересчёт перезаписывает."""

    __tablename__ = "decision_pre_approved_offers"

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    max_amount: Mapped[Decimal] = mapped_column(MONEY)
    rate_from: Mapped[Decimal] = mapped_column(RATE)
    term_max_months: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(String(16))
    factors_summary: Mapped[list[str]] = mapped_column(JSONType)
    valid_until: Mapped[date] = mapped_column(Date)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
