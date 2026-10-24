"""SQLAlchemy-модели scoring. Таблицы с префиксом `scoring_`."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Uuid
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
    # Качество данных (scoring_0004): ok / degraded и почему; до неё — пусто.
    quality: Mapped[str | None] = mapped_column(String(16), default=None)
    quality_reasons: Mapped[list[str] | None] = mapped_column(JSONType, default=None)


class FeatureSnapshotRecord(Base):
    """Хранилище признаков клиента (scoring_0005): признаки клиента на дату снимка обогащения."""

    __tablename__ = "scoring_feature_snapshots"
    __table_args__ = (
        Index("ix_scoring_feature_snapshots_organization", "organization_id", "as_of"),
        Index("ix_scoring_feature_snapshots_enrichment", "enrichment_snapshot_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    as_of: Mapped[date] = mapped_column(Date)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enrichment_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    features: Mapped[dict[str, Any]] = mapped_column(JSONType)
    sources: Mapped[list[str]] = mapped_column(JSONType)
    version: Mapped[str] = mapped_column(String(32))
