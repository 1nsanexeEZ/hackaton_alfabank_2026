"""SQLAlchemy-модели decision. Таблицы с префиксом `decision_`."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
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
    # policy_v3 (decision_0002): мягкие триггеры и ставка по компонентам.
    triggers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, default=None)
    rate_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONType, default=None)


class FounderPrescreenRecord(Base):
    """Предскрин учредителя стартапа; повторная проверка — новая строка, действует последняя."""

    __tablename__ = "decision_founder_prescreens"
    __table_args__ = (Index("ix_decision_founder_prescreens_org", "organization_id", "checked_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    founder_account_id: Mapped[UUID] = mapped_column(Uuid)
    founder_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    version: Mapped[str] = mapped_column(String(32))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
    # Ключевая, с которой посчитано: сменилась — ночной пакет пересчитает.
    key_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)


class ProjectAssessmentRecord(Base):
    """Проектная оценка стартапа; повторная оценка — новая строка, действует последняя."""

    __tablename__ = "decision_project_assessments"
    __table_args__ = (
        Index("ix_decision_project_assessments_org", "organization_id", "checked_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    product_code: Mapped[str] = mapped_column(String(32))
    plan_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    # Что просили и цифры финмодели на запрошенной сумме (ProjectFigures), суммы строками.
    figures: Mapped[dict[str, Any]] = mapped_column(JSONType)
    max_amount: Mapped[Decimal | None] = mapped_column(MONEY, default=None)
    version: Mapped[str] = mapped_column(String(32))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DecisionPolicyVersionRecord(Base):
    """Версии кредитной политики, которые ведёт админ (decision_0005): черновик → активная →
    архив. Встроенной политики из YAML здесь нет — она действует, пока нет активной версии."""

    __tablename__ = "decision_policy_versions"
    __table_args__ = (
        # Активной бывает только одна версия.
        Index(
            "uq_decision_policy_versions_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    version: Mapped[str] = mapped_column(String(32), primary_key=True)  # policy_v10.1
    status: Mapped[str] = mapped_column(String(16))
    # Тот же документ, что YAML: Decimal строками, `version` внутри — код версии.
    body: Mapped[dict[str, Any]] = mapped_column(JSONType)
    based_on: Mapped[str | None] = mapped_column(String(32), default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
